# -*- coding: utf-8 -*-
"""
片库影视 - 4k01.pianku.online（发布页 fb.pianku.online，同构域名 4k01-03）
MacCMS 10 + 2_fixed 模板，仅保留在线播放线路（腾讯/爱奇艺/优酷等官方页面）。

关键结论（实测验证）：
1. 分类 /vodshow/{tid}-----------.html（第1页）；分页 /vodshow/{tid}--------{pg}---.html
   tid: 20电影 37剧集 43动漫 45综艺 47B站番剧
2. 首页/分类/搜索卡片：.vod-item > a[href=/voddetail/{id}.html]（img 封面 / .remarks 备注 / .title 片名）
3. 详情页 /voddetail/{id}.html：
   片名 h1.detail-title（含 .detail-remarks 状态）、detail-meta 分类/地区/年份/语言/导演/主演、
   简介 .detail-desc p、
   线路 tab .source-tab-item[data-target=playlist-{sid}] 文本（腾讯/奇异/优酷…）
   集数 a[href=/vodplay/{id}-{sid}-{nid}.html] 按 sid 分组
4. 播放页 /vodplay/{id}-{sid}-{nid}.html：var player_aaaa={"encrypt":0,"url":"https://v.qq.com/...","from":"qq"}
   url 是官方平台页面（非直链）→ playerContent 返回 parse=1 交给壳子解析器处理
5. 搜索 /vodsearch/-------------.html?key=关键词（标准 MacCMS，结果同为 vod-item 卡片）
说明：本站在线线路均为腾讯/爱奇艺/优酷官方页面，未提供 m3u8 直链；
网盘/磁力资源（需 Cloudflare Turnstile 人机验证）不在本源范围内。
"""
import re
import json
import time
import urllib.parse

try:
    import requests
except ImportError:
    requests = None

import urllib.request
import urllib.error

try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def __init__(self):
            pass


class Spider(Spider):
    name = "片库"
    base_url = "https://4k01.pianku.online"
    site_url = "https://4k01.pianku.online"
    searchable = 1
    quickSearch = 1
    filterable = 0
    changeable = 1

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://4k01.pianku.online/",
    }

    # 分类（tid 来自首页导航）
    class_name = ["电影", "剧集", "动漫", "综艺", "B站"]
    class_url = ["20", "37", "43", "45", "47"]
    CATEGORY_MAP = {"20": "电影", "37": "剧集", "43": "动漫", "45": "综艺", "47": "B站"}

    def __init__(self):
        super().__init__()
        self._session = None
        self._urllib = None
        self._play_cache = {}
        self._cache_ts = {}

    # ==================== 工具 ====================
    def _log(self, msg):
        try:
            print("[%s] %s" % (self.name, msg))
        except Exception:
            pass

    @staticmethod
    def _clean(text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text))).strip()

    # ==================== 网络层（requests→urllib 双通道） ====================
    def _init_http(self):
        if self._session is None and requests is not None:
            try:
                s = requests.Session()
                s.verify = False
                s.trust_env = False
                self._session = s
                try:
                    requests.packages.urllib3.disable_warnings()
                except Exception:
                    pass
            except Exception:
                self._session = None
        if self._urllib is None:
            try:
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                self._urllib = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(context=ctx))
            except Exception:
                self._urllib = None

    def _get(self, url, timeout=15):
        self._init_http()
        if self._session is not None:
            try:
                r = self._session.get(url, headers=self.headers, timeout=timeout)
                return r.status_code, r.text
            except Exception as e:
                self._log("requests 失败: %s" % e)
        if self._urllib is not None:
            try:
                req = urllib.request.Request(url, headers=self.headers)
                resp = self._urllib.open(req, timeout=timeout)
                return resp.getcode(), resp.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                try:
                    return e.code, e.read().decode("utf-8", "ignore")
                except Exception:
                    return e.code, ""
            except Exception as e:
                self._log("urllib 失败: %s" % e)
        return 0, ""

    # ==================== 卡片解析 ====================
    def _parse_vod_items(self, html):
        """vod-item 卡片：href=/voddetail/{id}.html + img 封面 + remarks + title"""
        videos = []
        seen = set()
        for m in re.finditer(
                r'<a href="/voddetail/(\d+)\.html"[^>]*title="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL):
            vod_id = m.group(1)
            if vod_id in seen:
                continue
            inner = m.group(3)
            pm = re.search(r'<img[^>]*src="([^"]+)"', inner)
            rm = re.search(r'class="remarks"[^>]*>\s*([^<]+)', inner)
            seen.add(vod_id)
            videos.append({
                "vod_id": vod_id,
                "vod_name": m.group(2).strip(),
                "vod_pic": pm.group(1) if pm else "",
                "vod_remarks": rm.group(1).strip() if rm else "",
            })
        return videos

    # ==================== TVBox 接口 ====================
    def init(self, extend=''):
        try:
            kv = {}
            for part in str(extend or "").split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    kv[k.strip().lower()] = v.strip()
            if kv.get("url"):
                self.base_url = kv["url"].rstrip("/")
                self.site_url = self.base_url
                self.headers["Referer"] = self.base_url + "/"
            self._init_http()
            self._log("初始化完成: %s" % self.base_url)
        except Exception as e:
            self._log("init 异常: %s" % e)

    def homeContent(self, filter=False):
        result = {
            "class": [{"type_id": tid, "type_name": name}
                      for tid, name in zip(self.class_url, self.class_name)]
        }
        if filter:
            result["filters"] = {}
            result["filter"] = {}
        return result

    def homeVideoContent(self):
        try:
            code, html = self._get(self.base_url + "/")
            if code != 200:
                return {"list": []}
            videos = self._parse_vod_items(html)
            seen = set()
            dedup = []
            for v in videos:
                if v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    dedup.append(v)
            return {"list": dedup[:40]}
        except Exception as e:
            self._log("homeVideoContent 异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            tid = str(tid)
            if tid not in self.CATEGORY_MAP:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            if pg == 1:
                url = "%s/vodshow/%s-----------.html" % (self.base_url, tid)
            else:
                url = "%s/vodshow/%s--------%d---.html" % (self.base_url, tid, pg)
            self._log("分类请求: " + url)
            code, html = self._get(url)
            if code != 200:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            videos = self._parse_vod_items(html)
            pagecount = pg + 1 if len(videos) >= 24 else pg
            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": 24,
                "total": pagecount * 24,
            }
        except Exception as e:
            self._log("categoryContent 异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            try:
                pg = max(1, int(pg or 1))
            except (TypeError, ValueError):
                pg = 1
            keyword = str(key or "").strip()
            if not keyword:
                return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
            url = "%s/vodsearch/-------------.html?wd=%s" % (self.base_url, urllib.parse.quote(keyword))
            self._log("搜索请求: %s quick=%s" % (url, quick))
            code, html = self._get(url)
            if code != 200:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            videos = self._parse_vod_items(html)
            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 24,
                "total": 999999,
            }
        except Exception as e:
            self._log("searchContent 异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = str(ids[0] if isinstance(ids, list) else ids)
            url = "%s/voddetail/%s.html" % (self.base_url, vod_id)
            code, html = self._get(url)
            if code != 200:
                return {"list": []}
            # ---- 基本信息 ----
            title = re.search(r'<h1[^>]*class="detail-title"[^>]*>(.*?)</h1>', html, re.DOTALL)
            vod_name = ""
            vod_remarks = ""
            if title:
                inner = title.group(1)
                tm = re.search(r'<span[^>]*class="detail-remarks"[^>]*>([^<]+)</span>', inner)
                if tm:
                    vod_remarks = tm.group(1).strip()
                vod_name = re.sub(r"<span[^>]*>.*?</span>", "", inner).strip()
            # 封面
            vod_pic = ""
            pm = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html) or \
                 re.search(r'<div[^>]*class="detail-pic"[^>]*>\s*<img[^>]*src="([^"]+)"', html) or \
                 re.search(r'<img[^>]*src="(https?://[^"]+)"[^>]*alt="' + re.escape(vod_name) + '"', html)
            if pm:
                vod_pic = pm.group(1)
            # detail-meta 字段（一个 div 内含多个 span）
            vod_area = ""
            vod_year = ""
            vod_actor = ""
            vod_director = ""
            for m in re.finditer(r'<div class="detail-meta">(.*?)</div>', html, re.DOTALL):
                for span in re.finditer(r'<span>([^<]+)</span>', m.group(1)):
                    txt = span.group(1).strip()
                    if txt.startswith("地区"):
                        vod_area = txt.split("：")[-1]
                    elif txt.startswith("年份"):
                        vod_year = txt.split("：")[-1]
                    elif txt.startswith("导演"):
                        vod_director = txt.split("：")[-1]
                    elif txt.startswith("主演"):
                        vod_actor = txt.split("：")[-1]
            # 简介
            vod_content = ""
            dm = re.search(r'<div[^>]*class="detail-desc"[^>]*>\s*<h3>[^<]*</h3>\s*<p>(.*?)</p>', html, re.DOTALL)
            if dm:
                vod_content = self._clean(dm.group(1))
            # ---- 线路 + 集数 ----
            groups = {}
            for m in re.finditer(r'href="/vodplay/%s-(\d+)-(\d+)\.html"[^>]*>\s*([^<]{1,15}?)\s*</a>' % vod_id, html):
                sid, nid, name = m.groups()
                groups.setdefault(sid, []).append((int(nid), name.strip()))
            if not groups:
                for m in re.finditer(r'href="/vodplay/(\d+)-(\d+)-(\d+)\.html"[^>]*>\s*([^<]{1,15}?)\s*</a>', html):
                    vid, sid, nid, name = m.groups()
                    if vid != vod_id:
                        continue
                    groups.setdefault(sid, []).append((int(nid), name.strip()))
            if not groups:
                self._log("详情无在线线路: %s" % vod_id)
                return {"list": []}
            # 线路名：source-tab-item[data-target=playlist-{sid}]
            tab_map = {}
            for m in re.finditer(r'class="source-tab-item"[^>]*data-target="playlist-(\d+)"[^>]*>\s*([^<]{1,10}?)\s*</span>', html):
                tab_map[m.group(1)] = m.group(2).strip()
            sorted_sids = sorted(groups.keys(), key=lambda s: (min(n[0] for n in groups[s]), int(s)))
            from_list = []
            url_list = []
            for sid in sorted_sids:
                eps = sorted(groups[sid], key=lambda x: x[0])
                src_name = tab_map.get(sid, "线路%s" % sid)
                from_list.append(src_name)
                url_list.append("#".join(
                    "%s$%s|%s|%s" % (n, sid, nid, vod_id) for _nid, n in eps))
            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_year": vod_year,
                "vod_area": vod_area,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_content": vod_content,
                "vod_remarks": vod_remarks,
                "vod_play_from": "$$$".join(from_list),
                "vod_play_url": "$$$".join(url_list),
            }
            self._log("详情成功: %s 线路: %s" % (vod_name, "/".join(from_list)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent 异常: %s" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = [p.strip() for p in str(id).split("|")]
            if len(parts) != 3:
                return {"parse": 0, "url": "", "header": ""}
            sid, nid, vod_id = parts
            url = "%s/vodplay/%s-%s-%s.html" % (self.base_url, vod_id, sid, nid)
            code, html = self._get(url)
            if code != 200:
                return {"parse": 0, "url": "", "header": ""}
            m = re.search(r'var\s+player_aaaa\s*=\s*', html)
            if not m:
                return {"parse": 0, "url": "", "header": ""}
            start = m.end()
            while start < len(html) and html[start] != "{":
                start += 1
            depth = 1
            i = start + 1
            in_str = False
            esc = False
            while i < len(html) and depth > 0:
                c = html[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                else:
                    if c == '"':
                        in_str = True
                    elif c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                i += 1
            if depth != 0:
                return {"parse": 0, "url": "", "header": ""}
            try:
                pd = json.loads(html[start:i])
            except Exception:
                return {"parse": 0, "url": "", "header": ""}
            enc_url = (pd.get("url") or "").strip()
            if not enc_url:
                return {"parse": 0, "url": "", "header": ""}
            encrypt = str(pd.get("encrypt", "0"))
            if encrypt == "1":
                enc_url = urllib.parse.unquote(enc_url)
            elif encrypt == "2":
                try:
                    import base64
                    enc_url = urllib.parse.unquote(
                        base64.b64decode(enc_url).decode("utf-8", "ignore"))
                except Exception:
                    pass
            self._log("播放地址: %s... (from=%s)" % (enc_url[:60], pd.get("from", "")))
            is_direct = bool(re.search(r"\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)", enc_url, re.I))
            # 官方平台页面（v.qq.com / iqiyi / youku）→ parse=1 交给系统解析器
            return {
                "parse": 0 if is_direct else 1,
                "url": enc_url,
                "header": {"User-Agent": self.headers["User-Agent"],
                           "Referer": self.base_url + "/"},
            }
        except Exception as e:
            self._log("playerContent 异常: %s" % e)
            return {"parse": 0, "url": "", "header": ""}

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