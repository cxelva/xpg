# -*- coding: utf-8 -*-
"""
追影影视 - www.zhuiying1.com（备用 www.zhuiying.app）
MacCMS 10 + 自研 v6 模板 + 自建 player_api 防盗链解密

关键结论（逆向实测验证）：
1. 分类列表：/vodshow/{tid}-----------.html（第1页）；分页 /vodshow/{tid}--------{pg}---.html
   ★ 分页必须用数字 tid（拼音分页 404），tid: 1电影 2电视剧 3动漫 4综艺 5短剧
   筛选：地区 {tid}-{地区}--------{pg}---.html；年份 {tid}-{年份}-----------.html
        排序 {tid}--{sort}--------{pg}---.html（sort: hits_week/id/douban_score）
   卡片：<a class="card js-card-item" href="/video/{hash}.html"><img src=封面 alt=名><span class="card-status">备注</span><div class="card-title">片名
   首页热搜榜：<a class="hotsearch_hot_item" href=.. title=片名><img class="hotsearch_item_img" src=封面>
2. 详情页 /video/{hash}.html：
   片名 h1.detail-title、年份 span.detail-year、豆瓣 m-val-highlight、类型/地区 .matrix-item span.m-val、
   导演/主演 .actor-line、简介 #synopsisContent、
   线路 source-tab[data-target=ep-list-N] 的 tab-name；集数 a[href=/play/{hash}-{sid}-{n}.html] 按 sid 分组
3. 播放页 /play/{hash}-{sid}-{n}.html：
   window.MAC_PLAY_CONFIG = {vod_id, sid, nid, baseKey, requestUrl, poster, videoTitle}
   签名：token = md5(baseKey + timestamp + UserAgent)   ★ UA 必须与 HTTP 请求完全一致
   POST /player_api.php  form: url={requestUrl百分号编码}&timestamp&token
   必带 X-Requested-With: XMLHttpRequest + Referer + 会话 Cookie
   响应 data → atob(data.split('').reverse().join('')) → JSON {jmurl, urltype} 即真实直链
   ★ 防盗链核心坑：requestUrl 含 +/= 必须 percent-encoding（不编码 = 403 签名拦截）
4. 搜索：/index.php/vod/search.html?wd=关键词（结果同为 card js-card-item 卡片）
5. 直链 nbyjson NBY m3u8，无 Referer 可直接播放（已验证）
"""
import re
import json
import hashlib
import base64
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
    name = "追影"
    site_url = "https://www.zhuiying1.com"
    base_url = "https://www.zhuiying1.com"
    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

    # 分类（数字 tid 是分页/筛选的必要参数；短剧真实 tid=26，tid=5 为空分类）
    CATEGORY = [
        ("1", "电影"), ("2", "电视剧"), ("3", "动漫"), ("4", "综艺"), ("26", "短剧"),
    ]
    CATEGORY_MAP = {"1": "电影", "2": "电视剧", "3": "动漫", "4": "综艺", "26": "短剧"}

    SORTS = [("", "默认"), ("time", "最新"), ("hits_week", "周热"), ("douban_score", "评分")]
    AREAS = ["", "中国大陆", "中国香港", "中国台湾", "美国", "日本", "韩国", "英国", "法国", "泰国", "印度"]
    YEARS = ["", "2026", "2025", "2024", "2023", "2022", "2021", "2020",
             "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010"]

    def __init__(self):
        super().__init__()
        self._http = None
        self._urllib_opener = None
        self._play_cache = {}
        self._play_cache_ts = {}
        self._detail_cache = {}
        self._detail_cache_ts = {}
        self._re_card = None

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
        text = re.sub(r"<[^>]+>", "", str(text))
        return re.sub(r"\s+", " ", text).strip()

    def _parse_card(self, html, include_hot=True):
        """卡片解析：include_hot=True 时含首页热搜榜；分类/搜索页传 False 排除全局热搜"""
        videos = []
        seen = set()
        # 模式 1：搜索页 hero-card（精确命中主卡）
        for m in re.finditer(
                r'<a[^>]+href="(/video/[^"]+)"[^>]*class="hero-card-thumb"[^>]*title="([^"]*)"[^>]*>(.*?)</a>',
                html, re.DOTALL):
            vod_id = m.group(1).split("/")[-1].replace(".html", "")
            if vod_id in seen:
                continue
            inner = m.group(3)
            pm = re.search(r'<img[^>]*src="([^"]+)"', inner)
            rm = re.search(r'class="hero-thumb-remark"[^>]*>\s*([^<]+)', inner)
            seen.add(vod_id)
            videos.append({
                "vod_id": vod_id,
                "vod_name": m.group(2).strip(),
                "vod_pic": pm.group(1) if pm else "",
                "vod_remarks": rm.group(1).strip() if rm else "",
            })
        # 模式 2：搜索页 search-list-card
        for m in re.finditer(
                r'<div class="search-list-card[^"]*"[^>]*>\s*<a[^>]+href="(/video/[^"]+)"[^>]*class="list-card-thumb"[^>]*title="([^"]*)"[^>]*>(.*?)</a>',
                html, re.DOTALL):
            vod_id = m.group(1).split("/")[-1].replace(".html", "")
            if vod_id in seen:
                continue
            inner = m.group(3)
            pm = re.search(r'<img[^>]*src="([^"]+)"', inner)
            rm = re.search(r'class="list-thumb-remark"[^>]*>\s*([^<]+)', inner)
            seen.add(vod_id)
            videos.append({
                "vod_id": vod_id,
                "vod_name": m.group(2).strip(),
                "vod_pic": pm.group(1) if pm else "",
                "vod_remarks": rm.group(1).strip() if rm else "",
            })
        # 模式 3：card js-card-item / hotsearch_hot_item
        for m in re.finditer(r'<a[^>]+href="(/video/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            if any(v["vod_id"] == m.group(1).split("/")[-1].replace(".html", "") for v in videos):
                continue
            attrs = m.group(0)
            is_card = "card js-card-item" in attrs
            is_hot = "hotsearch_hot_item" in attrs
            if not (is_card or (include_hot and is_hot)):
                continue
            vod_id = m.group(1).split("/")[-1].replace(".html", "")
            if vod_id in seen:
                continue
            inner = m.group(2)
            # 封面：card-cover img / hotsearch_item_img
            pm = re.search(r'class="(?:hotsearch_item_img|card-cover)[^"]*"[^>]*>\s*<img[^>]*src="([^"]+)"', inner) or \
                 re.search(r'<img[^>]*class="[^"]*hotsearch_item_img[^"]*"[^>]*src="([^"]+)"', inner)
            pic = pm.group(1) if pm else ""
            # 片名：title 属性 / card-title / hotsearch_item_title
            nm = re.search(r'title="([^"]+)"', m.group(0))
            name = ""
            if nm:
                name = nm.group(1)
            if not name:
                nm2 = re.search(r'class="card-title"[^>]*>([^<]+)<', inner) or \
                      re.search(r'class="hotsearch_item_title"[^>]*>([^<]+)<', inner)
                if nm2:
                    name = nm2.group(1).strip()
            if not name:
                nm3 = re.search(r'alt="([^"]+)"', inner)
                if nm3:
                    name = nm3.group(1)
            # 备注：card-status / hotsearch 徽标
            rm = re.search(r'class="card-status"[^>]*>([^<]+)<', inner)
            note = rm.group(1).strip() if rm else ""
            if not note:
                rm2 = re.search(r'class="[^"]*hotsearch_item_badge[^"]*"[^>]*>([^<]+)<', inner)
                note = rm2.group(1).strip() if rm2 else ""
            seen.add(vod_id)
            videos.append({
                "vod_id": vod_id,
                "vod_name": name.strip(),
                "vod_pic": pic,
                "vod_remarks": note,
            })
        return videos

    # ==================== 网络层 ====================
    def _init_http(self):
        if self._http is None and requests is not None:
            try:
                s = requests.Session()
                s.verify = False
                s.trust_env = False
                self._http = s
                try:
                    requests.packages.urllib3.disable_warnings()
                except Exception:
                    pass
            except Exception:
                self._http = None
        if self._urllib_opener is None:
            try:
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                handlers = [urllib.request.ProxyHandler({}),
                            urllib.request.HTTPSHandler(context=ctx)]
                self._urllib_opener = urllib.request.build_opener(*handlers)
            except Exception:
                self._urllib_opener = None

    def _raw(self, url, method="GET", body=None, headers=None, timeout=15):
        """返回 (status, text)；requests → urllib 双通道"""
        if self._http is not None:
            try:
                if method == "GET":
                    r = self._http.get(url, headers=headers, timeout=timeout)
                else:
                    r = self._http.post(url, data=body, headers=headers, timeout=timeout)
                return r.status_code, r.text
            except Exception as e:
                self._log("requests 通道失败: %s" % e)
        self._init_http()
        if self._urllib_opener is not None:
            try:
                data = body.encode("utf-8") if body and method == "POST" else None
                req = urllib.request.Request(url, data=data, headers=headers or {})
                req.get_method = lambda: method
                resp = self._urllib_opener.open(req, timeout=timeout)
                return resp.getcode(), resp.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                try:
                    return e.code, e.read().decode("utf-8", "ignore")
                except Exception:
                    return e.code, ""
            except Exception as e:
                self._log("urllib 通道失败: %s" % e)
        return 0, ""

    def _get_html(self, url, referer=None, cookie_jar=None, retry=2):
        """页面抓取 + 会话复用"""
        for attempt in range(retry):
            try:
                if self._http is not None:
                    kw = {}
                    if cookie_jar:
                        kw["cookies"] = cookie_jar
                    r = self._http.get(url, headers={
                        "User-Agent": self.UA,
                        "Accept-Language": "zh-CN,zh;q=0.9",
                        "Referer": referer or self.base_url + "/",
                    }, timeout=15, **kw)
                    return r.status_code, r.text
                self._init_http()
                req = urllib.request.Request(url, headers={
                    "User-Agent": self.UA,
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Referer": referer or self.base_url + "/",
                })
                resp = self._urllib_opener.open(req, timeout=15)
                return resp.getcode(), resp.read().decode("utf-8", "ignore")
            except Exception as e:
                self._log("抓取失败(%s): %s" % (attempt, e))
                time.sleep(0.6)
        return 0, ""

    # ==================== TVBox 核心 ====================
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
            self._init_http()
            self._log("初始化完成: %s" % self.base_url)
        except Exception as e:
            self._log("init 异常: %s" % e)

    def homeContent(self, filter=False):
        result = {"class": [{"type_id": tid, "type_name": name}
                            for tid, name in self.CATEGORY]}
        if filter:
            filters = {}
            for tid, name in self.CATEGORY:
                fl = []
                fl.append({"key": "sort", "name": "排序",
                           "value": [{"n": v[1], "v": v[0]} for v in self.SORTS]})
                fl.append({"key": "year", "name": "年份",
                           "value": [{"n": v if v else "全部", "v": v} for v in self.YEARS]})
                fl.append({"key": "area", "name": "地区",
                           "value": [{"n": v if v else "全部", "v": v} for v in self.AREAS]})
                filters[name] = fl
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        try:
            code, html = self._get_html(self.base_url)
            if code != 200:
                return {"list": []}
            videos = self._parse_card(html)
            return {"list": videos[:40]}
        except Exception as e:
            self._log("homeVideoContent 异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            tid = str(tid)
            if tid not in self.CATEGORY_MAP:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            # 筛选解析
            area = ""
            year = ""
            sort = ""
            if content:
                try:
                    c = json.loads(content) if isinstance(content, str) else (content or {})
                except Exception:
                    c = {}
                if isinstance(c, dict):
                    area = str(c.get("area") or "")
                    year = str(c.get("year") or "")
                    sort = str(c.get("sort") or "")
            # 筛选解析
            area = ""
            year = ""
            sort = ""
            if content:
                try:
                    c = json.loads(content) if isinstance(content, str) else (content or {})
                except Exception:
                    c = {}
                if isinstance(c, dict):
                    area = str(c.get("area") or "")
                    year = str(c.get("year") or "")
                    sort = str(c.get("sort") or "")
            # AJAX 接口：/index.php/ajax/vod_list?id=&class=&area=&year=&by=&page=&limit=
            params = {
                "id": tid,
                "class": "",
                "area": area,
                "year": year,
                "by": sort,
                "page": pg,
                "limit": 27,
            }
            url = self.base_url + "/index.php/ajax/vod_list?" + urllib.parse.urlencode(params)
            resp_code, text = self._raw(url, method="GET", headers={
                "User-Agent": self.UA,
                "Referer": self.base_url + "/vodshow/%s-----------.html" % tid,
                "X-Requested-With": "XMLHttpRequest",
            })
            videos = []
            pagecount = pg
            if resp_code in (200, 201):
                try:
                    j = json.loads(text)
                except Exception:
                    j = {}
                if j.get("code") == 1:
                    for item in (j.get("list") or []):
                        vid = str(item.get("vod_id") or "")
                        if not vid:
                            continue
                        videos.append({
                            "vod_id": vid,
                            "vod_name": item.get("vod_name") or "",
                            "vod_pic": item.get("vod_pic") or "",
                            "vod_remarks": item.get("vod_remarks") or "",
                        })
                    pagecount = pg + 1 if len(videos) >= 27 else pg
            if not videos:
                # 兜底：HTML 解析
                url2 = "%s/vodshow/%s-----------.html" % (self.base_url, tid)
                if pg > 1:
                    url2 = "%s/vodshow/%s--------%d---.html" % (self.base_url, tid, pg)
                code, html = self._get_html(url2, referer=self.base_url + "/")
                if code == 200:
                    videos = self._parse_card(html, include_hot=False)
                    pagecount = pg + 1 if len(videos) >= 24 else pg
            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": 27,
                "total": pagecount * 27,
            }
        except Exception as e:
            self._log("categoryContent 异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 27, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            try:
                pg = max(1, int(pg or 1))
            except (TypeError, ValueError):
                pg = 1
            keyword = str(key or "").strip()
            if not keyword:
                return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
            url = "%s/index.php/vod/search.html?wd=%s" % (self.base_url, urllib.parse.quote(keyword))
            code, html = self._get_html(url, referer=self.base_url + "/")
            if code != 200:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            videos = self._parse_card(html, include_hot=False)
            if not quick and not pg == 1:
                pass
            return {
                "list": videos,
                "page": pg,
                "pagecount": 1,
                "limit": 24,
                "total": 0,
            }
        except Exception as e:
            self._log("searchContent 异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = str(ids[0] if isinstance(ids, list) else ids).replace(".html", "")
            url = "%s/video/%s.html" % (self.base_url, vod_id)
            code, html = self._get_html(url, referer=self.base_url + "/")
            if code != 200:
                return {"list": []}
            # ---- 基本信息 ----
            title = re.search(r'<h1[^>]*class="detail-title"[^>]*>([^<]+)</h1>', html)
            vod_name = title.group(1).strip() if title else ""
            ym = re.search(r'<span[^>]*class="detail-year"[^>]*>\(?([^)]*)\)?</span>', html)
            vod_year = ym.group(1).strip() if ym else ""
            pic = ""
            pm = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html) or \
                 re.search(r"<meta[^>]*property='og:image'[^>]*content='([^']+)'", html)
            if pm:
                pic = pm.group(1)
            if not pic:
                pm2 = re.search(r'class="[^"]*cinematic-bg[^"]*"[^>]*style="[^"]*url\(\'([^\']+)\'\)', html)
                pic = pm2.group(1) if pm2 else ""
            # 豆瓣评分/类型/地区
            score = ""
            m = re.search(r'class="m-val m-val-highlight"[^>]*>\s*([\d.]+)\s*<', html)
            if m:
                score = m.group(1)
            vod_area = ""
            m = re.search(r'制片国家/地区</span>\s*</div>\s*<div[^>]*>\s*<span[^>]*>\s*([^<]+)\s*</span>', html)
            if not m:
                m = re.search(r'<span class="m-val"[^>]*>\s*([\u4e00-\u9fff]+)\s*</span>\s*<span class="m-lbl">制片国家/地区</span>', html)
            if m:
                vod_area = m.group(1).strip()
            vod_actor = ""
            m = re.search(r'<span class="label">主演:</span>\s*<span[^>]*class="val[^"]*"[^>]*>([^<]+)</span>', html)
            if m:
                vod_actor = self._clean(m.group(1))
            vod_director = ""
            m = re.search(r'<span class="label">导演:</span>\s*<span[^>]*class="val[^"]*"[^>]*>([^<]+)</span>', html)
            if m:
                vod_director = self._clean(m.group(1))
            vod_content = ""
            m = re.search(r'class="synopsis-text"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                vod_content = self._clean(m.group(1))
            vod_remarks = ""
            t = re.search(r'<title>([^<]+)</title>', html)
            if t:
                parts = t.group(1).split(" - ")
                if len(parts) >= 2:
                    vod_remarks = parts[1].strip()
            # ---- 线路 + 集数 ----
            groups = {}
            for m in re.finditer(r'href="(/play/%s-(\d+)-(\d+)\.html)"[^>]*>\s*([^<]+?)\s*</a>' % vod_id, html):
                href, sid, nid, name = m.groups()
                groups.setdefault(sid, []).append((int(nid), name.strip(), href))
            if not groups:
                # 兜底：任意 hash 的 play 链接（当前详情页的）
                for m in re.finditer(r'href="(/play/[^"]+-(\d+)-(\d+)\.html)"[^>]*>\s*([^<]+?)\s*</a>', html):
                    href, sid, nid, name = m.groups()
                    groups.setdefault(sid, []).append((int(nid), name.strip(), href))
                if groups:
                    vod_id = "__any__"
            if not groups:
                self._log("详情无播放源: %s" % vod_id)
                return {"list": []}
            # 线路名（tab-name ↔ data-target ep-list-N，sid 与链接一致）
            tab_map = {}
            for m in re.finditer(r'<div class="source-tab" data-target="([^"]+)"[^>]*>\s*<span class="tab-name">([^<]+)</span>', html):
                tab_map[m.group(1)] = m.group(2).strip()
            sorted_sids = sorted(groups.keys(), key=lambda s: (min(n[0] for n in groups[s]), int(s)))
            from_list = []
            url_list = []
            for sid in sorted_sids:
                eps = sorted(groups[sid], key=lambda x: x[0])
                # 找此 sid 的线路名：ep-list-{sid} 的 tab
                src_name = tab_map.get("ep-list-%s" % sid, "线路%s" % sid)
                from_list.append(src_name)
                url_list.append("#".join(
                    "%s$%s|%s|%s" % (n, sid, nid, vod_id) for _nid, n, href in eps))
            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": pic,
                "vod_year": vod_year,
                "vod_area": vod_area,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_content": vod_content,
                "vod_remarks": vod_remarks,
                "vod_score": score,
                "vod_play_from": "$$$".join(from_list),
                "vod_play_url": "$$$".join(url_list),
            }
            self._log("详情成功: %s 线路: %s" % (vod_name, "/".join(from_list)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent 异常: %s" % e)
            return {"list": []}

    # ---------- 播放解密 ----------
    def _decode_play(self, sid, nid, vod_id):
        """抓播放页 → MAC_PLAY_CONFIG → /player_api.php → 直链"""
        try:
            if vod_id == "__any__":
                return None, "无法定位播放页"
            url = "%s/play/%s-%s-%s.html" % (self.base_url, vod_id, sid, nid)
            code, html = self._get_html(url, referer=self.base_url + "/video/%s.html" % vod_id)
            if code != 200:
                return None, "播放页抓取失败 (%s)" % code
            m = re.search(r"MAC_PLAY_CONFIG\s*=\s*(\{.*?\})\s*;", html, re.DOTALL)
            if not m:
                return None, "播放页无 MAC_PLAY_CONFIG"
            cfg = dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', m.group(1)))
            base_key = cfg.get("baseKey", "")
            req_url = cfg.get("requestUrl", "")
            if not base_key or not req_url:
                return None, "播放配置字段缺失"
            ts = str(int(time.time()))
            token = hashlib.md5((base_key + ts + self.UA).encode("utf-8")).hexdigest()
            body = urllib.parse.urlencode({"url": req_url, "timestamp": ts, "token": token})
            resp_code, text = self._raw(
                self.base_url + "/player_api.php", method="POST", body=body,
                headers={
                    "User-Agent": self.UA,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": url,
                    "Origin": self.base_url,
                })
            if resp_code not in (200, 201):
                return None, "player_api HTTP %s" % resp_code
            try:
                res = json.loads(text)
            except Exception:
                return None, "player_api 响应非 JSON"
            if res.get("error"):
                return None, "player_api: %s" % res["error"]
            data = res.get("data", "")
            if not data:
                return None, "player_api 无 data"
            try:
                dec = base64.b64decode(data[::-1] + "=" * (-len(data) % 4)).decode("utf-8", "ignore")
                parsed = json.loads(dec)
            except Exception:
                return None, "解密失败"
            jmurl = parsed.get("jmurl") or parsed.get("url") or ""
            if not jmurl:
                return None, "解密结果无 jmurl"
            return jmurl, ""
        except Exception as e:
            return None, "解码异常: %s" % e

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = [p.strip() for p in str(id).split("|")]
            if len(parts) != 3:
                return {"parse": 0, "url": "", "header": ""}
            sid, nid, vod_id = parts
            jmurl, tip = self._decode_play(sid, nid, vod_id)
            if not jmurl:
                self._log("播放失败: %s" % tip)
                return {"parse": 0, "url": "", "header": "", "error": tip}
            self._log("解码成功: %s..." % jmurl[:80])
            return {
                "parse": 0,
                "url": jmurl,
                "header": {"User-Agent": self.UA, "Referer": self.base_url + "/"},
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