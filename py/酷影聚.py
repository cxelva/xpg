# -*- coding: utf-8 -*-
"""
酷影聚 - 多源聚合影视源（kyj1.cc 同款聚合玩法）

站点本质：kyj1.cc 自己不存资源，是一个"多源聚合搜索平台"：
  前端 JS 通过 proxy.php 代理 17 个第三方 MacCMS 资源站 API（ac=list 搜索 / ac=detail 详情），
  结果合并去重展示，播放页按 source 参数取对应资源站直链，非直链用各源"解析器"(logo 字段)兜底。

本源直接内置 13 个可用资源 API（不依赖 kyj1.cc 服务器，更稳）：
  1. 搜索：全部源并行搜索（ThreadPoolExecutor 限 6 并发），按源优先级顺序合并、按 (源, vod_id) 去重，
     非 quick 模式按片名相似度排序
  2. 分类：西瓜源子类 tid（父类无数据），探测首个 >=5 条的 tid 并缓存
  3. 详情：并行拉各源 ac=detail，跨源合并全部线路（同一片在不同源可同时出多条线路），
     并补全片名/封面/演员/简介；过滤"全非直链且源无解析器"的死线路
  4. 播放：m3u8/mp4 等直链直接 parse=0 返回；非直链用该源 logo 解析器；再不行交壳子 WebView 兜底

关键验证（2026-10-11 实测）：
  - 西瓜直链 svip.xgplay17.com/{date}/{hash}/index.m3u8 无需防盗链头，master/子流/ts 全通；
    非凡/量子/光速/最大等跨源 m3u8 直链同样 200 可达
  - 西瓜分类按子类 tid（t=2 父类仅 1 条假数据，t=13 国产剧 8067 条）
  - 13 个可用源：西瓜/天堂/非凡/量子/光速/极速/暴风/新浪/最大/七异/猫眼/解析1/解析2；
    高清=IP白名单、速播/红牛/ck 连不通，已从内置列表移除
  - MacCMS API 列表接口普遍无 vod_pic（仅量子搜索响应带图），封面靠详情补全
"""
import re
import json
import time
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:
    requests = None

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def __init__(self):
            pass


class Spider(Spider):
    # ==================== 基础配置 ====================
    name = "酷影聚"
    base_url = "https://kyj1.cc"
    site_url = "https://kyj1.cc"

    searchable = 1
    quickSearch = 1
    filterable = 0
    changeable = 1

    # 顶级分类 -> 西瓜源候选 tid（父类无数据，子类优先；探测阈值 5 条）
    CATEGORY_TIDS = {
        "电影": ["6", "1", "7", "8", "9", "10", "11", "12", "20", "34", "37"],
        "电视剧": ["13", "2", "14", "15", "16", "21", "22", "23", "24"],
        "综艺": ["25", "3", "26", "27", "28"],
        "动漫": ["29", "4", "30", "31", "32", "33"],
        "短剧": ["36", "38", "39", "40", "41", "42", "43", "44", "45"],
    }
    class_name = list(CATEGORY_TIDS.keys())
    class_url = list(CATEGORY_TIDS.keys())

    # 13 个可用资源站（2026-10-11 实测；高清=IP白名单/速播/红牛/ck 连不通，已移除）
    # 顺序 = kyj1.cc link.php 后台排序；量子源 ac=list 搜索响应带 vod_pic
    SOURCES = [
        {"name": "西瓜", "url": "https://xiguazy.tv/api.php/provide/vod/at/json/?ac=videolist", "logo": ""},
        {"name": "天堂", "url": "http://dyttzy.tv/api.php/provide/vod/at/json/?ac=videolist", "logo": ""},
        {"name": "非凡", "url": "http://ffzy.tv/api.php/provide/vod/at/json/?ac=videolist", "logo": ""},
        {"name": "量子", "url": "https://cj.lziapi.com/api.php/provide/vod/at/json/?ac=videolist", "logo": ""},
        {"name": "光速", "url": "https://api.guangsuapi.com/api.php/provide/vod/at/json/?ac=videolist", "logo": ""},
        {"name": "极速", "url": "https://jszyapi.com/api.php/provide/vod/at/json/?ac=videolist", "logo": ""},
        {"name": "暴风", "url": "https://bfzyapi.com/api.php/provide/vod/from/bfzym3u8/", "logo": ""},
        {"name": "新浪", "url": "https://api.xinlangapi.com/xinlangapi.php/provide/vod/from/xlm3u8", "logo": ""},
        {"name": "最大", "url": "https://api.zuidapi.com/api.php/provide/vod/from/zuidam3u8/", "logo": ""},
        {"name": "七异", "url": "https://www.iqiyizyapi.com/api.php/provide/vod/?ac=list", "logo": ""},
        {"name": "猫眼", "url": "https://api.maoyanapi.top/api.php/provide/vod/at/json", "logo": ""},
        {"name": "解析1", "url": "https://zy.jinchanjiexi.net/api.php/provide/vod/?ac=list", "logo": "https://bfq.txnp.cn/excessive?url="},
        {"name": "解析2", "url": "https://cj.jusj.top/api.php/provide/vod/at/json/", "logo": "https://free.maccms.xyz/?url="},
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    MAX_WORKERS = 6
    API_TIMEOUT = 8
    SEARCH_TIMEOUT = 9
    DETAIL_TIMEOUT = 6

    _re_name_garbage = re.compile(
        r'[\s\-_]*(?:HD|TC|TS|抢先版|枪版|DVD|BD|1080P|720P|4K|2K|高清|超清|蓝光|国语|粤语|中字|中英双字|完整版|全集|未删减版|(?:第[0-9一二三四五六七八九十]+[集季期]))\s*$',
        re.I)
    _re_direct = re.compile(r'\.(m3u8|mp4|flv|ts|ogg|m4a|mkv|webm)([?#&]|$)', re.I)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._sessions = {}
        self._play_cache = {}
        self._detail_cache = {}
        self._cache_ttl = 900
        self._last_req_time = {}
        self._min_req_interval = 0.3
        # tid 可用性缓存（避免每次分类都探测）
        self._tid_ok = {}

    # ==================== 工具 ====================
    def _log(self, msg):
        print("[%s] %s" % (self.name, msg))

    def _clean_vod_name(self, name):
        if not name:
            return name
        prev = name
        while True:
            cleaned = self._re_name_garbage.sub('', prev).strip()
            if cleaned == prev:
                break
            prev = cleaned
        return prev

    def _clean_html(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _src_by_url(self, url):
        for s in self.SOURCES:
            if s["url"] == url:
                return s
        return None

    def _api_url(self, src, ac, **params):
        """拼接资源 API 请求 URL（兼容 URL 自带 ? 或无 ? 的格式）"""
        url = src["url"]
        sep = "&" if "?" in url else "?"
        if ac == "list":
            parts = ["%s%sac=list" % (url, sep)]
            wd = params.get("wd")
            if wd:
                parts.append("wd=" + urllib.parse.quote(wd))
            tid = params.get("t")
            if tid:
                parts.append("t=%s" % tid)
            pg = params.get("pg", "1")
            parts.append("pg=%s" % pg)
            return "&".join(parts)
        if ac == "detail":
            return "%s%sac=detail&ids=%s" % (url, sep, params["ids"])
        return url

    # ==================== 请求 ====================
    def _request(self, src, url, timeout=8):
        """requests 主通道 + urllib 兜底，UTF-8 强制解码"""
        headers = self.headers.copy()
        headers["Referer"] = self._origin(src["url"])
        self._rate_limit(src["url"])
        # 通道1：requests
        if requests:
            try:
                resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
                ct = resp.headers.get("Content-Type", "")
                if "charset=" in ct:
                    enc = ct.split("charset=")[-1].split(";")[0].strip()
                    if enc and enc.lower() not in ("utf-8", "utf8"):
                        try:
                            raw = resp.content
                            text = raw.decode(enc, errors="ignore")
                            return text
                        except Exception:
                            pass
                resp.encoding = "utf-8"
                return resp.text
            except Exception:
                pass
        # 通道2：urllib（带独立 opener，verify=False）
        try:
            import ssl
            import urllib.request
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read()
                return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _origin(self, url):
        m = re.match(r'(https?://[^/]+)', url)
        if not m:
            return url
        return m.group(1) + "/"

    def _rate_limit(self, key):
        with self._lock:
            now = time.time()
            last = self._last_req_time.get(key, 0)
            gap = now - last
            if 0 < gap < self._min_req_interval:
                time.sleep(self._min_req_interval - gap)
            self._last_req_time[key] = time.time()

    def _get_json(self, src, url, timeout=10):
        text = self._request(src, url, timeout=timeout)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    # ==================== 搜索 ====================
    def _search_one(self, src, wd, pg):
        url = self._api_url(src, "list", wd=wd, pg=pg)
        data = self._get_json(src, url, timeout=self.API_TIMEOUT)
        if not data or not data.get("list"):
            return src, []
        items = []
        for v in data["list"]:
            vid = v.get("vod_id")
            if vid is None:
                continue
            items.append({
                "vod_id": "%s|%s" % (src["url"], vid),
                "vod_name": self._clean_vod_name(v.get("vod_name", "")),
                "vod_pic": (v.get("vod_pic") or "").strip(),
                "vod_remarks": (v.get("vod_remarks") or "").strip(),
                "_src": src["url"],
                "_src_name": src["name"],
                "_vid": str(vid),
            })
        return src["url"], items

    def searchContent(self, key, quick=False, pg="1"):
        try:
            try:
                pg = max(1, int(pg or 1))
            except (TypeError, ValueError):
                pg = 1
            keyword = str(key or "").strip()
            if not keyword:
                return {"page": pg, "pagecount": 1, "limit": 0, "total": 0, "list": []}
            self._log("搜索: %s pg=%s quick=%s" % (keyword, pg, quick))
            results = {}
            order = []
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as ex:
                futs = {ex.submit(self._search_one, s, keyword, pg): s for s in self.SOURCES}
                deadline = time.time() + self.SEARCH_TIMEOUT
                for f in futs:
                    remain = deadline - time.time()
                    if remain <= 0:
                        break
                    try:
                        key, items = f.result(timeout=min(remain, 1.5))
                        if key not in results:
                            order.append(key)
                        results[key] = items
                    except Exception:
                        pass
            videos = []
            seen = set()
            for k in order:
                for it in results[k]:
                    dk = (k, it["_vid"])
                    if dk in seen:
                        continue
                    seen.add(dk)
                    videos.append(it)
            if not quick:
                kw = keyword.lower()
                def _score(v):
                    nm = v["vod_name"].lower()
                    if nm == kw:
                        return 0
                    if nm.startswith(kw):
                        return 1
                    if kw in nm:
                        return 2
                    return 3
                videos.sort(key=_score)
            self._log("搜索完成: %s 命中 %d" % (keyword, len(videos)))
            return {
                "list": videos[:100],
                "page": pg,
                "pagecount": 1,
                "limit": 20,
                "total": len(videos),
            }
        except Exception as e:
            self._log("searchContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    # ==================== 首页/分类 ====================
    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": tid, "type_name": name}
                for name, tids in self.CATEGORY_TIDS.items()
                for tid in [tids[0]]
            ]
        }
        if filter:
            result["filters"] = {}
            result["filter"] = {}
        return result

    def _fetch_category(self, src, tid, pg):
        url = self._api_url(src, "list", t=tid, pg=pg)
        data = self._get_json(src, url, timeout=self.API_TIMEOUT)
        return data or {}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            if str(tid) not in self.CATEGORY_TIDS:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
            cands = self.CATEGORY_TIDS[str(tid)]
            src = self.SOURCES[1]  # 分类主源：西瓜
            # 探测第一个有数据的 tid（>=5 条才算可用，避免父类 1-3 条"假数据"）
            used_tid = None
            for t in cands:
                if t in self._tid_ok:
                    if self._tid_ok[t]:
                        used_tid = t
                        break
                    continue
                data = self._fetch_category(src, t, 1)
                ok = len(data.get("list") or []) >= 5
                self._tid_ok[t] = ok
                if ok:
                    used_tid = t
                    break
            if not used_tid:
                used_tid = cands[0]
            data = self._fetch_category(src, used_tid, pg)
            videos = []
            for v in data.get("list") or []:
                vid = v.get("vod_id")
                if vid is None:
                    continue
                videos.append({
                    "vod_id": "%s|%s" % (src["url"], vid),
                    "vod_name": self._clean_vod_name(v.get("vod_name", "")),
                    "vod_pic": (v.get("vod_pic") or "").strip(),
                    "vod_remarks": (v.get("vod_remarks") or "").strip(),
                    "_src": src["url"],
                    "_src_name": src["name"],
                    "_vid": str(vid),
                })
            try:
                pagecount = max(1, int(data.get("pagecount") or 1))
            except (TypeError, ValueError):
                pagecount = 1
            try:
                total = int(data.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": 20,
                "total": total,
            }
        except Exception as e:
            self._log("categoryContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    def homeVideoContent(self):
        # 首页推荐 = 西瓜最新更新（ac=list 无 t 参数）
        try:
            src = self.SOURCES[1]
            url = self._api_url(src, "list", pg="1")
            data = self._get_json(src, url, timeout=self.API_TIMEOUT)
            videos = []
            for v in (data.get("list") or [])[:30]:
                vid = v.get("vod_id")
                if vid is None:
                    continue
                videos.append({
                    "vod_id": "%s|%s" % (src["url"], vid),
                    "vod_name": self._clean_vod_name(v.get("vod_name", "")),
                    "vod_pic": (v.get("vod_pic") or "").strip(),
                    "vod_remarks": (v.get("vod_remarks") or "").strip(),
                })
            return {"list": videos}
        except Exception as e:
            self._log("homeVideoContent异常: %s" % e)
            return {"list": []}

    # ==================== 详情（跨源聚合线路） ====================
    def _detail_one(self, src, vid):
        url = self._api_url(src, "detail", ids=vid)
        data = self._get_json(src, url, timeout=self.API_TIMEOUT)
        if not data or not data.get("list"):
            return None
        v = data["list"][0]
        return {
            "_src": src["url"],
            "_src_name": src["name"],
            "_vid": str(vid),
            "vod_name": v.get("vod_name", ""),
            "vod_pic": (v.get("vod_pic") or "").strip(),
            "vod_actor": (v.get("vod_actor") or "").strip(),
            "vod_director": (v.get("vod_director") or "").strip(),
            "vod_year": (v.get("vod_year") or "").strip(),
            "vod_area": (v.get("vod_area") or "").strip(),
            "vod_lang": (v.get("vod_lang") or "").strip(),
            "vod_class": (v.get("vod_class") or "").strip(),
            "vod_remarks": (v.get("vod_remarks") or "").strip(),
            "vod_content": self._clean_html(v.get("vod_content") or ""),
            "vod_play_from": v.get("vod_play_from") or "",
            "vod_play_url": v.get("vod_play_url") or "",
        }

    def detailContent(self, ids):
        try:
            raw = ids[0] if isinstance(ids, list) else str(ids)
            if "|" in raw:
                src_url, vid = raw.rsplit("|", 1)
            else:
                src_url, vid = self.SOURCES[0]["url"], raw
            src = self._src_by_url(src_url) or self.SOURCES[0]
            # 缓存
            cache_key = "%s|%s" % (src["url"], vid)
            now = time.time()
            if cache_key in self._detail_cache:
                data, ts = self._detail_cache[cache_key]
                if now - ts < self._cache_ttl:
                    return {"list": [data]}

            base = self._detail_one(src, vid)
            if not base:
                return {"list": []}

            video = {
                "vod_id": raw,
                "vod_name": base["vod_name"] or "未知",
                "vod_pic": base["vod_pic"],
                "vod_year": base["vod_year"],
                "vod_area": base["vod_area"],
                "vod_lang": base["vod_lang"],
                "vod_class": base["vod_class"],
                "vod_actor": base["vod_actor"],
                "vod_director": base["vod_director"],
                "vod_content": base["vod_content"],
                "vod_remarks": base["vod_remarks"],
            }

            # 其他源并行补线路 + 补字段
            extra = []
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as ex:
                futs = []
                for s in self.SOURCES:
                    if s["url"] == src["url"]:
                        continue
                    futs.append((s, ex.submit(self._detail_one, s, vid)))
                deadline = time.time() + self.DETAIL_TIMEOUT
                for s, f in futs:
                    remain = deadline - time.time()
                    if remain <= 0:
                        break
                    try:
                        r = f.result(timeout=max(0.1, remain))
                        if r:
                            extra.append(r)
                    except Exception:
                        pass

            # 合并线路：主源线路在前，其他源线路也带（线路名保持原名，播放链接含源 url 可路由）
            plays = self._merge_plays(base, src)
            for d in extra:
                if d["vod_play_url"]:
                    plays.extend(self._merge_plays(d))
                # 字段补全
                if not video["vod_pic"] and d["vod_pic"]:
                    video["vod_pic"] = d["vod_pic"]
                if not video["vod_actor"] and d["vod_actor"]:
                    video["vod_actor"] = d["vod_actor"]
                if not video["vod_content"] and d["vod_content"]:
                    video["vod_content"] = d["vod_content"]
                if not video["vod_remarks"] and d["vod_remarks"]:
                    video["vod_remarks"] = d["vod_remarks"]
                if not video["vod_year"] and d["vod_year"]:
                    video["vod_year"] = d["vod_year"]

            # 线路清洗：过滤"全非直链且源无解析器"的死线路；播放链接自造 5 段格式：vid|src|线路|集名|真实URL
            cleaned = []
            for s, line_name, eps in plays:
                if all(not self._re_direct.search(link) for _, link in eps):
                    if not (s and s.get("logo")):
                        continue
                s_url = s["url"] if s else src["url"]
                good = []
                for ep_name, link in eps:
                    play_id = "%s|%s|%s|%s|%s" % (
                        vid, s_url, line_name, ep_name, link)
                    good.append("%s$%s" % (ep_name, play_id))
                if good:
                    cleaned.append((line_name, "#".join(good)))
            if not cleaned:
                return {"list": []}
            video["vod_play_from"] = "$$$".join(n for n, _ in cleaned)
            video["vod_play_url"] = "$$$".join(u for _, u in cleaned)
            self._detail_cache[cache_key] = (video, now)
            self._log("详情OK: %s 线路 %d 条" % (video["vod_name"], len(cleaned)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent异常: %s" % e)
            return {"list": []}

    def _merge_plays(self, d, src=None):
        """把单个源 detail 的 from/url 拆成 [(源dict, 线路名, [(集名, 链接)...])]"""
        result = []
        s = src or (self._src_by_url(d.get("_src")) if d.get("_src") else None)
        froms = (d.get("vod_play_from") or "").split("$$$")
        urls = (d.get("vod_play_url") or "").split("$$$")
        for i, fr in enumerate(froms):
            fr = (fr or "").strip()
            if not fr:
                continue
            eps = []
            url_part = urls[i] if i < len(urls) else ""
            for ep in url_part.split("#"):
                ep = ep.strip()
                if not ep:
                    continue
                if "$" in ep:
                    nm, link = ep.rsplit("$", 1)
                else:
                    nm, link = "", ep
                if not link:
                    continue
                eps.append((nm.strip(), link.strip()))
            if eps:
                result.append((s, fr, eps))
        return result

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags=None):
        try:
            # id 格式：vid|srcUrl|线路名|集名|链接（自定义拼接，见 detailContent）
            if "|" not in str(id):
                return {"parse": 0, "url": str(id), "header": ""}
            parts = str(id).split("|", 4)
            if len(parts) < 4:
                return {"parse": 0, "url": str(id), "header": ""}
            _vid, src_url, _line, ep_name, link = parts
            src = self._src_by_url(src_url) or self.SOURCES[0]
            link = link.strip()
            self._log("播放: [%s] %s" % (src["name"], link[:80]))
            is_direct = bool(self._re_direct.search(link))
            if is_direct:
                h = self.headers.copy()
                h["Referer"] = self._origin(src["url"])
                h["Accept"] = "*/*"
                return {"parse": 0, "url": link, "header": h}
            # 非直链：源带解析器就用解析器
            if src.get("logo"):
                jh_url = src["logo"] + urllib.parse.quote(link, safe="")
                return {"parse": 1, "url": jh_url, "header": ""}
            # 无解析器：交系统解析
            return {"parse": 1, "url": link, "header": ""}
        except Exception as e:
            self._log("playerContent异常: %s" % e)
            return {"parse": 0, "url": "", "header": ""}

    def init(self, extend=''):
        self._log("初始化完成")

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass