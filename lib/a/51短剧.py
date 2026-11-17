# -*- coding: utf-8 -*-
"""
51短剧 spider (fixed 2026-11)
Site structure changed: /play/{id}/{ep}/ + Nuxt  ->  /video/{id}/ + /video/{id}/ep-{n}/ + JSON-LD
"""
import re
import sys
import json
import html as html_lib
import urllib.parse
import urllib.request
import http.cookiejar
import ssl

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):
    host = "https://blue.xdrgcewe.cc"
    UA = (
        "Mozilla/5.0 (Linux; Android 13; Mobile) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    categories = [
        {"type_name": "首页推荐", "type_id": "home"},
        {"type_name": "排行榜", "type_id": "rank"},
        {"type_name": "最新", "type_id": "new"},
        {"type_name": "热门推荐", "type_id": "recommend"},
        {"type_name": "AI成人短剧", "type_id": "ai-duanju"},
        {"type_name": "AI成人漫剧", "type_id": "ai-manju"},
        {"type_name": "AI换脸", "type_id": "ai-huanlian"},
        {"type_name": "AI魔改", "type_id": "ai-mogai"},
    ]

    def init(self, extend=""):
        self.host = "https://blue.xdrgcewe.cc"
        ext = (extend or "").strip()
        if ext.startswith("http"):
            self.host = ext.rstrip("/")
        elif ext.startswith("{"):
            try:
                cfg = json.loads(ext)
                if cfg.get("host"):
                    self.host = str(cfg["host"]).rstrip("/")
            except Exception:
                pass
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
            "Cache-Control": "no-cache",
        }
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE
        self._cj = http.cookiejar.CookieJar()

    def getName(self):
        return "51短剧"

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(?:m3u8|mp4|flv)(?:$|[?#])", str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return

    def destroy(self):
        return

    # -------------------- public API --------------------

    def homeContent(self, filter):
        html = self._get("/")
        videos = self._parse_list(html)
        return {
            "class": list(self.categories),
            "filters": {},
            "list": videos[:40],
        }

    def homeVideoContent(self):
        html = self._get("/")
        return {"list": self._parse_list(html)[:40]}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        tid = str(tid or "home")

        if tid == "home":
            if page != 1:
                return {"list": [], "page": page, "pagecount": 1, "limit": 40, "total": 0}
            path = "/"
        elif tid == "rank":
            path = "/ranks/hot/" if page == 1 else "/ranks/hot/page/%d/" % page
        elif tid == "new":
            path = "/newest" if page == 1 else "/newest/page/%d/" % page
        elif tid == "recommend":
            path = "/recommend" if page == 1 else "/recommend/page/%d/" % page
        elif tid in ("ai-duanju", "ai-manju", "ai-huanlian", "ai-mogai"):
            path = "/%s/" % tid if page == 1 else "/%s/page/%d/" % (tid, page)
        else:
            # allow custom path / filter id
            tid_q = urllib.parse.quote(str(tid), safe="-_/")
            path = "/%s/" % tid_q.lstrip("/")
            if page > 1:
                path = path.rstrip("/") + "/page/%d/" % page

        html = self._get(path)
        videos = self._parse_list(html)
        if tid == "home":
            return {
                "list": videos[:40],
                "page": 1,
                "pagecount": 1 if videos else 0,
                "limit": 40,
                "total": len(videos),
            }
        # heuristic pagination
        has_more = len(videos) >= 15
        pagecount = page + 1 if has_more else page
        return {
            "list": videos,
            "page": page,
            "pagecount": max(pagecount, page),
            "limit": len(videos) or 30,
            "total": pagecount * (len(videos) or 30),
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        kw = urllib.parse.quote(str(key or "").strip(), safe="")
        if not kw:
            return {"list": [], "page": page, "pagecount": 0, "limit": 30, "total": 0}
        path = "/search/video/%s/" % kw if page == 1 else "/search/video/%s/page/%d/" % (kw, page)
        html = self._get(path)
        videos = self._parse_list(html)
        has_more = len(videos) >= 15
        pagecount = page + 1 if has_more else (1 if videos else 0)
        return {
            "list": videos,
            "page": page,
            "pagecount": max(pagecount, page),
            "limit": len(videos) or 30,
            "total": pagecount * (len(videos) or 30),
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        raw = str(ids[0]).strip()
        # accept video/123, play/123/1, plain id, or 123/ep-2
        m = re.search(r"(?:video|play)/(\d+)", raw)
        if m:
            vid = m.group(1)
        else:
            m2 = re.search(r"(\d+)", raw)
            vid = m2.group(1) if m2 else raw
        if not vid:
            return {"list": []}

        html = self._get("/video/%s/" % vid)
        if not html:
            return {"list": []}

        meta = self._parse_detail_meta(html, vid)
        episodes = self._parse_episodes(html, vid)
        if not episodes:
            # at least one episode (the main page itself)
            episodes = [{"id": "1", "name": "第1集"}]

        play_items = []
        for ep in episodes:
            eid = str(ep.get("id") or ep.get("index") or "").strip()
            name = str(ep.get("name") or "").strip() or ("第%s集" % eid)
            if not eid:
                continue
            # play id format: vid/ep  (ep=1 means base page)
            play_items.append("%s$%s/%s" % (name, vid, eid))

        if not play_items:
            return {"list": []}

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": meta["vod_name"] or ("短剧%s" % vid),
                "vod_pic": meta["vod_pic"] or self._cover_url(vid),
                "vod_content": meta["vod_content"] or meta["vod_name"],
                "vod_play_from": "51短剧",
                "vod_play_url": "#".join(play_items),
                "vod_remarks": meta.get("remarks") or ("全%d集" % len(play_items)),
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        val = str(id or "").strip()
        if "$" in val:
            val = val.split("$")[-1].strip()
        if self.isVideoFormat(val) and val.startswith("http"):
            if self._probe_media(val):
                return {"parse": 0, "url": val, "header": self._play_headers()}
            return {"parse": 1, "url": val, "header": self._play_headers()}

        vid, ep = "", "1"
        m = re.search(r"(?:video/|play/)?(\d+)(?:/(?:ep-)?(\d+))?", val)
        if m:
            vid = m.group(1)
            if m.group(2):
                ep = m.group(2)
        else:
            m2 = re.search(r"(\d+)", val)
            if m2:
                vid = m2.group(1)
        if not vid:
            return {"parse": 0, "url": "", "msg": "invalid id"}

        # build page path
        if str(ep) in ("1", "01", ""):
            page = "/video/%s/" % vid
        else:
            page = "/video/%s/ep-%s/" % (vid, str(int(ep)) if ep.isdigit() else ep)

        html = self._get(page)
        m3u8 = self._extract_m3u8(html, prefer_index=int(ep) if str(ep).isdigit() else 1)
        if m3u8 and self._probe_media(m3u8):
            return {
                "parse": 0,
                "url": m3u8,
                "header": self._play_headers(),
            }
        # fallback: any m3u8 without probe
        if m3u8:
            return {
                "parse": 0,
                "url": m3u8,
                "header": self._play_headers(),
            }
        return {
            "parse": 1,
            "url": self._full_url(page),
            "header": self._play_headers(),
        }

    def localProxy(self, param):
        return None

    # -------------------- helpers --------------------

    def _play_headers(self):
        return {
            "User-Agent": self.UA,
            "Referer": self.host + "/",
            "Origin": self.host,
            "Accept": "*/*",
        }

    def _raw_get(self, url, timeout=25):
        try:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self._cj),
                urllib.request.HTTPSHandler(context=self._ssl_ctx),
            )
            req = urllib.request.Request(url, headers=self.headers)
            with opener.open(req, timeout=timeout) as resp:
                data = resp.read()
                # gzip
                if data[:2] == b"\x1f\x8b":
                    try:
                        import gzip
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                enc = resp.headers.get_content_charset() or "utf-8"
                return data.decode(enc, errors="ignore")
        except Exception:
            return ""

    def _normalize_html(self, rsp):
        """兼容 OK影视 / TVBox 各种 fetch 返回值。"""
        if rsp is None:
            return ""
        if isinstance(rsp, (bytes, bytearray)):
            data = bytes(rsp)
            if data[:2] == b"\x1f\x8b":
                try:
                    import gzip
                    data = gzip.decompress(data)
                except Exception:
                    pass
            return data.decode("utf-8", errors="ignore")
        if isinstance(rsp, str):
            return rsp
        # requests.Response / 自定义对象
        if hasattr(rsp, "text") and isinstance(rsp.text, str) and rsp.text:
            return rsp.text
        if hasattr(rsp, "content"):
            try:
                c = rsp.content
                if isinstance(c, (bytes, bytearray)):
                    if c[:2] == b"\x1f\x8b":
                        import gzip
                        c = gzip.decompress(c)
                    return c.decode("utf-8", errors="ignore")
                if isinstance(c, str):
                    return c
            except Exception:
                pass
        # dict: {"content": "..."} / {"data": "..."} / {"body": "..."}
        if isinstance(rsp, dict):
            for k in ("content", "data", "body", "html", "text", "result"):
                v = rsp.get(k)
                if isinstance(v, str) and len(v) > 50:
                    return v
                if isinstance(v, (bytes, bytearray)):
                    return self._normalize_html(v)
            # nested
            if "data" in rsp and isinstance(rsp["data"], dict):
                return self._normalize_html(rsp["data"])
        return str(rsp) if rsp else ""

    def _get(self, path_or_url, timeout=25):
        if path_or_url.startswith("http"):
            url = path_or_url
        else:
            url = self.host.rstrip("/") + (
                path_or_url if path_or_url.startswith("/") else "/" + path_or_url
            )
        html = ""
        # 1) 优先用壳子自带的 fetch（OK影视 / TVBox）
        try:
            if hasattr(self, "fetch"):
                try:
                    rsp = self.fetch(url, headers=self.headers)
                except TypeError:
                    # 有的版本 fetch 只接受 url
                    rsp = self.fetch(url)
                html = self._normalize_html(rsp)
        except Exception:
            html = ""
        # 2) 部分壳子用 self.request / self.getHtml
        if len(html) < 200:
            for attr in ("request", "getHtml", "get_html"):
                try:
                    fn = getattr(self, attr, None)
                    if not callable(fn):
                        continue
                    try:
                        rsp = fn(url, headers=self.headers)
                    except TypeError:
                        rsp = fn(url)
                    html = self._normalize_html(rsp)
                    if len(html) >= 200:
                        break
                except Exception:
                    pass
        # 3) 原生 urllib 兜底
        if len(html) < 200:
            html = self._raw_get(url, timeout=timeout)
        return html or ""

    def _full_url(self, u):
        if not u:
            return ""
        u = str(u).strip().replace("\\u002F", "/").replace("\\/", "/")
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return self.host.rstrip("/") + (u if u.startswith("/") else "/" + u)

    def _cover_url(self, vid):
        return self.host.rstrip("/") + "/share/video/%s/cover" % vid

    def _parse_jsonld(self, html):
        items = []
        if not html:
            return items
        for m in re.finditer(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
            html,
            re.I,
        ):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            items.append(data)
        return items

    def _walk_jsonld(self, data):
        """Yield all dict nodes from JSON-LD (handles @graph)."""
        if isinstance(data, dict):
            yield data
            for v in data.values():
                for x in self._walk_jsonld(v):
                    yield x
        elif isinstance(data, list):
            for v in data:
                for x in self._walk_jsonld(v):
                    yield x

    def _parse_list(self, html):
        """Parse video list from home / category / search pages."""
        results = []
        seen = set()
        if not html:
            return results

        def add(vid, name, remark=""):
            vid = str(vid).strip()
            name = html_lib.unescape(str(name or "")).strip()
            if not vid or vid in seen:
                return
            if not name or name in ("广告", "更多", "查看", "null", "undefined"):
                return
            seen.add(vid)
            results.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._cover_url(vid),
                "vod_remarks": str(remark or "").strip(),
            })

        # 1) JSON-LD ItemList（正式解析）
        for root in self._parse_jsonld(html):
            for node in self._walk_jsonld(root):
                if node.get("@type") != "ItemList":
                    continue
                for el in node.get("itemListElement") or []:
                    if not isinstance(el, dict):
                        continue
                    name = str(el.get("name") or "").strip()
                    url = str(el.get("url") or el.get("item") or "").strip()
                    if isinstance(el.get("item"), dict):
                        url = str(el["item"].get("url") or url)
                        if not name:
                            name = str(el["item"].get("name") or "")
                    m = re.search(r"/video/(\d+)", url)
                    if m and name:
                        add(m.group(1), name)

        # 2) 不依赖完整 JSON：从源码里直接抠 "name":"...","url":".../video/ID/"
        if len(results) < 5:
            for m in re.finditer(
                r'"name"\s*:\s*"([^"]{2,80})"\s*,\s*"position"\s*:\s*\d+\s*,\s*"url"\s*:\s*"[^"]*?/video/(\d+)/?"',
                html,
            ):
                add(m.group(2), m.group(1))
            for m in re.finditer(
                r'"url"\s*:\s*"[^"]*?/video/(\d+)/?"\s*,\s*"name"\s*:\s*"([^"]{2,80})"',
                html,
            ):
                add(m.group(1), m.group(2))
            for m in re.finditer(
                r'"name"\s*:\s*"([^"]{2,80})"\s*,\s*"url"\s*:\s*"[^"]*?/video/(\d+)/?"',
                html,
            ):
                add(m.group(2), m.group(1))

        # 3) 正则：href + 附近标题
        if len(results) < 5:
            markers = [m.start() for m in re.finditer(
                r'data-xpch=|class="[^"]*(?:card|item|video|drama|list)[^"]*"', html, re.I
            )]
            for link in re.finditer(r'href=["\']/video/(\d+)/["\']', html, re.I):
                vid = link.group(1)
                if vid in seen:
                    continue
                lefts = [p for p in markers if p <= link.start()]
                rights = [p for p in markers if p > link.start()]
                left = lefts[-1] if lefts else max(0, link.start() - 1500)
                right = rights[0] if rights else min(len(html), link.end() + 1000)
                block = html[left:right]
                title = ""
                for pat in (
                    r'alt=["\']([^"\']{2,60})["\']',
                    r'aria-label=["\']([^"\']{2,60})["\']',
                    r'title=["\']([^"\']{2,60})["\']',
                    r'>\s*([^<>]{2,40})\s*<',
                ):
                    tm = re.search(pat, block, re.I)
                    if tm:
                        t = html_lib.unescape(tm.group(1)).strip()
                        if t and t not in ("广告", "更多", "查看") and not t.startswith("http"):
                            title = t
                            break
                if title:
                    add(vid, title)

        # 4) 最后兜底：只有 id 也给出来，避免“分类有、内容空”
        if not results:
            for vid in re.findall(r"/video/(\d+)/", html):
                if vid in seen:
                    continue
                add(vid, "短剧%s" % vid)
                if len(results) >= 40:
                    break

        return results

    def _parse_detail_meta(self, html, vid):
        info = {
            "vod_name": "",
            "vod_content": "",
            "vod_pic": self._cover_url(vid),
            "remarks": "",
            "episodes": 1,
        }
        if not html:
            return info

        for root in self._parse_jsonld(html):
            for node in self._walk_jsonld(root):
                t = node.get("@type")
                if t == "VideoObject":
                    name = str(node.get("name") or "").strip()
                    name = re.sub(r"\s*第\d+集\s*$", "", name).strip()
                    if name:
                        info["vod_name"] = name
                    desc = str(node.get("description") or "").strip()
                    if desc:
                        info["vod_content"] = desc
                    thumbs = node.get("thumbnailUrl")
                    if isinstance(thumbs, list) and thumbs:
                        info["vod_pic"] = self._full_url(thumbs[0])
                    elif isinstance(thumbs, str) and thumbs:
                        info["vod_pic"] = self._full_url(thumbs)
                elif t == "WebPage":
                    name = str(node.get("name") or "").strip()
                    if name and not info["vod_name"]:
                        info["vod_name"] = name
                    desc = str(node.get("description") or "").strip()
                    if desc and not info["vod_content"]:
                        info["vod_content"] = desc
                    img = node.get("primaryImageOfPage")
                    if isinstance(img, dict):
                        cu = img.get("contentUrl") or img.get("url")
                        if cu:
                            info["vod_pic"] = self._full_url(cu)
                elif t == "ImageObject" and "cover" in str(node.get("contentUrl") or node.get("url") or ""):
                    cu = node.get("contentUrl") or node.get("url")
                    if cu:
                        info["vod_pic"] = self._full_url(cu)

        if not info["vod_name"]:
            tm = re.search(r"<title>([^<]+)</title>", html, re.I)
            if tm:
                t = tm.group(1).split("-")[0].split("|")[0].strip()
                t = re.sub(r"\s*第\d+集\s*$", "", t).strip()
                t = re.sub(r"[《》]", "", t).strip()
                info["vod_name"] = t
        if not info["vod_name"]:
            info["vod_name"] = "短剧%s" % vid
        return info

    def _parse_episodes(self, html, vid):
        """Collect episode numbers from /video/{id}/ep-N/ links."""
        nums = set()
        for n in re.findall(r"/video/%s/ep-(\d+)/" % re.escape(str(vid)), html):
            try:
                nums.add(int(n))
            except Exception:
                pass
        # main page is usually ep 1
        nums.add(1)
        episodes = []
        for i in sorted(nums):
            episodes.append({"id": str(i), "name": "第%d集" % i})
        return episodes

    def _extract_m3u8(self, html, prefer_index=1):
        if not html:
            return ""
        text = html_lib.unescape(html)
        text = text.replace("\\u002F", "/").replace("\\/", "/").replace("\\u0026", "&")
        candidates = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', text)
        # clean trailing junk
        cleaned = []
        seen = set()
        for u in candidates:
            u = u.rstrip("\\").split('"')[0].split("'")[0]
            u = html_lib.unescape(u)
            if u in seen:
                continue
            if "auth_key=" in u or "hls." in u or ".m3u8" in u:
                seen.add(u)
                cleaned.append(u)
        if not cleaned:
            return ""
        # prefer index (1-based) when multiple; otherwise first with auth_key
        idx = max(1, int(prefer_index or 1)) - 1
        if 0 <= idx < len(cleaned):
            return cleaned[idx]
        for u in cleaned:
            if "auth_key=" in u:
                return u
        return cleaned[0]

    def _probe_media(self, url):
        if not url or not str(url).lower().startswith(("http://", "https://")):
            return False
        try:
            req = urllib.request.Request(url, headers=self._play_headers(), method="GET")
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self._cj),
                urllib.request.HTTPSHandler(context=self._ssl_ctx),
            )
            with opener.open(req, timeout=12) as resp:
                data = resp.read(65536)
            body = data.decode("utf-8", errors="ignore").lstrip("\ufeff\r\n\t ")
            return bool(
                resp.status == 200
                and (
                    body.startswith("#EXTM3U")
                    or (self.isVideoFormat(url) and len(data) > 0)
                )
            )
        except Exception:
            return False
