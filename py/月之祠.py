# -*- coding: utf-8 -*-
"""
月之祠 - www.moonci.com
MacCMS 10 + conch 模板（服务端渲染）的二次元追番站。

关键结论（已实测验证）：
1. 站点本身可 curl 直连（首次偶发 403，重试即可；正常会话稳定 200）。
   CDN 名为 Dooki CDN，存在 mxa 前端挑战，但实测不影响正常 GET。
2. 页面结构（conch 模板）：
   - 分类页 /type/{tid}.html，分页 /type/{tid}/page/{pg}.html
     tid：新番 20 / 番剧 21 / 剧场 22
     卡片：a.hl-item-thumb[href="/anime/{id}.html"][title]，备注在 .hl-pic-text .remarks
   - 搜索 /search/{关键词}-------------.html（conch 模板固定格式）
   - 详情页 /anime/{id}.html：
     元数据在 li > em.hl-text-muted（主演/导演/年份/地区/类型/状态），简介在 meta description
     线路 tab：.hl-plays-from a.hl-tabs-btn（alt="X.1"/"X.3"）
     集数：a[href="/anime/{id}/play/{sid}-{nid}.html"]
   - 播放页 /anime/{id}/play/{sid}-{nid}.html：
     var player_aaaa={"from":"X_1","url":"<第三方播放页地址，percent-encoded>",...}
3. 播放直链需要两级解析（本插件核心难点）：
   a) player_aaaa.url 先 URL 解码 → 得到第三方地址（next.xifanacg.com/...）
   b) 请求本站播放器 /player/?url={第三方地址} → 返回 Yplayer 页面，
      内含 AES 加密的真实地址：encryptedUrl（base64）+ sessionKey
   c) 解密：base64 解码后，前 16 字节为 IV，其余为密文，
      AES-CBC / Pkcs7，key = sessionKey(utf-8)，解密即得真实 mp4/m3u8 直链
   d) 直链请求：不带 Referer 可正常 200（带第三方 Referer 反而 400）
4. 数据量：分类每页约 36 条；播放页 sid 为线路编号（1/2/...），nid 为集数序号。
"""
import re
import json
import time
import base64
import requests
import urllib.parse

try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def __init__(self):
            pass

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    _HAS_AES = True
except Exception:
    _HAS_AES = False


class Spider(Spider):
    # ==================== 基础配置 ====================
    name = "月之祠"
    base_url = "https://www.moonci.com"
    site_url = "https://www.moonci.com"

    searchable = 1
    quickSearch = 1
    filterable = 0

    # 分类（conch 模板 tid）
    class_name = ["新番", "番剧", "剧场"]
    class_url = ["20", "21", "22"]
    CATEGORY_NAMES = {"20": "新番", "21": "番剧", "22": "剧场"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.moonci.com/",
        "Connection": "keep-alive",
    }

    # 直链不要带 Referer，否则 CDN 返回 400
    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._play_cache = {}
        self._cache_ttl = 300   # 直链 sign 有时效，缓存 5 分钟
        self._last_req_time = 0
        self._min_req_interval = 0.6

    # ==================== 工具方法 ====================
    def _log(self, msg):
        print("[%s] %s" % (self.name, msg))

    def _clean_html(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        return re.sub(r'\s+', ' ', text).strip()

    # ==================== 请求基础 ====================
    def _apply_req_delay(self):
        now = time.time()
        elapsed = now - self._last_req_time
        if 0 < elapsed < self._min_req_interval:
            time.sleep(self._min_req_interval - elapsed)
        self._last_req_time = time.time()

    def _get(self, url, max_retry=3, timeout=15, params=None):
        for attempt in range(max_retry):
            try:
                self._apply_req_delay()
                resp = self._session.get(url, headers=self.headers, timeout=timeout, params=params)
                # 偶发 JS 挑战：403 且内容极短，重试
                if resp.status_code == 403 and len(resp.text) < 500:
                    self._log("403 挑战，重试 %s (%s/%s)" % (url, attempt + 1, max_retry))
                    if attempt < max_retry - 1:
                        time.sleep(0.8 + attempt)
                        continue
                return resp
            except Exception as e:
                self._log("请求失败 %s (%s/%s): %s" % (url, attempt + 1, max_retry, e))
                if attempt < max_retry - 1:
                    time.sleep(0.8 + attempt)
        return None

    # ==================== 列表解析 ====================
    def _parse_list(self, html):
        videos = []
        if not html:
            return videos
        # 卡片：a.hl-item-thumb[href=/anime/{id}.html][title=]，备注在同级 .hl-pic-text
        for m in re.finditer(
                r'<a[^>]*class="[^"]*hl-item-thumb[^"]*"[^>]*href="(/anime/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*>(.*?)</a>',
                html, re.DOTALL):
            _, vid, title, inner = m.groups()
            pic = ""
            pm = re.search(r'data-original="([^"]+)"', m.group(0))
            if pm:
                pic = pm.group(1)
            remarks = ""
            rm = re.search(r'class="[^"]*remarks[^"]*"[^>]*>([^<]*)<', inner)
            if rm:
                remarks = rm.group(1).strip()
            videos.append({
                "vod_id": vid,
                "vod_name": title.strip(),
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return videos

    # ==================== TVBox 核心方法 ====================
    def init(self, extend=''):
        self._log("初始化完成 AES=%s" % _HAS_AES)

    def homeContent(self, filter=False):
        return {
            "class": [
                {"type_id": tid, "type_name": name}
                for tid, name in self.CATEGORY_NAMES.items()
            ]
        }

    def homeVideoContent(self):
        try:
            html = self._get(self.base_url)
            videos = self._parse_list(html.text if html else "")
            seen = set()
            out = []
            for v in videos:
                if v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    out.append(v)
            return {"list": out[:30]}
        except Exception as e:
            self._log("homeVideoContent异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            if str(tid) not in self.CATEGORY_NAMES:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}
            if pg == 1:
                url = "%s/type/%s.html" % (self.base_url, tid)
            else:
                url = "%s/type/%s/page/%d.html" % (self.base_url, tid, pg)
            self._log("分类请求: tid=%s pg=%s" % (tid, pg))
            resp = self._get(url)
            html = resp.text if resp else ""
            videos = self._parse_list(html)
            # 从分页链接推断总页数
            pagecount = pg
            pages = [int(x) for x in re.findall(r'/type/%s/page/(\d+)\.html' % tid, html)]
            if pages:
                pagecount = max(pages)
            return {
                "list": videos,
                "page": pg,
                "pagecount": max(pagecount, pg),
                "limit": 36,
                "total": 0,
            }
        except Exception as e:
            self._log("categoryContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        pg = max(1, int(pg or 1))
        keyword = str(key or "").strip()
        if not keyword:
            return {"page": pg, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        try:
            # conch 搜索固定格式：/search/{kw}-------------.html
            kw = urllib.parse.quote(keyword)
            if pg == 1:
                url = "%s/search/%s-------------.html" % (self.base_url, kw)
            else:
                url = "%s/search/%s-------------/page/%d.html" % (self.base_url, kw, pg)
            self._log("搜索请求: %s pg=%s" % (keyword, pg))
            resp = self._get(url)
            videos = self._parse_list(resp.text if resp else "")
            if not quick:
                kl = keyword.lower()

                def _score(v):
                    n = (v.get("vod_name") or "").lower()
                    if n == kl:
                        return 0
                    if n.startswith(kl):
                        return 1
                    if kl in n:
                        return 2
                    return 3
                videos = sorted(videos, key=_score)
            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 36,
                "total": 0,
            }
        except Exception as e:
            self._log("searchContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}

    # ==================== 详情 ====================
    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            vod_id = str(vod_id).split("-")[0]
            url = "%s/anime/%s.html" % (self.base_url, vod_id)
            self._log("详情请求: %s" % url)
            resp = self._get(url)
            html = resp.text if resp else ""
            if not html:
                return {"list": []}

            vod_name = ""
            tm = re.search(r'<title>《([^》]+)》', html)
            if tm:
                vod_name = tm.group(1).strip()
            if not vod_name:
                tm = re.search(r'<h1[^>]*>([^<]*)</h1>', html)
                if tm:
                    vod_name = self._clean_html(tm.group(1))
            if not vod_name:
                vod_name = "未知"

            vod_pic = ""
            pm = re.search(r'class="[^"]*hl-item-thumb[^"]*"[^>]*data-original="([^"]+)"', html)
            if pm:
                vod_pic = pm.group(1)
            if not vod_pic:
                pm = re.search(r'<img[^>]*(?:data-original|data-src|src)="(https?://[^"]+)"', html)
                if pm:
                    vod_pic = pm.group(1)

            def _grab(label):
                m = re.search(r'<em[^>]*hl-text-muted[^>]*>%s[：:]</em>(.*?)</li>' % label, html, re.DOTALL)
                if m:
                    return self._clean_html(m.group(1))
                return ""

            vod_actor = _grab("主演")
            vod_director = _grab("导演")
            vod_year = _grab("年份")
            vod_area = _grab("地区")
            vod_remarks = _grab("状态")
            vod_class = _grab("类型")
            # 简介
            vod_content = ""
            mc = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
            if mc:
                vod_content = self._clean_html(mc.group(1))
                vod_content = vod_content.split("剧情介绍：")[-1] if "剧情介绍：" in vod_content else vod_content

            # 线路与集数
            sources = self._parse_play_sources(html, vod_id)
            if not sources:
                self._log("未能解析到播放源")
                return {"list": []}

            from_list = [s["source_name"] for s in sources]
            url_list = ["#".join("%s$%s" % (ep["name"], ep["link"]) for ep in s["episodes"])
                        for s in sources]

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
            self._log("详情解析成功: %s 线路: %s" % (vod_name, "$$$".join(from_list)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent异常: %s" % e)
            return {"list": []}

    def _parse_play_sources(self, html, vod_id):
        # 线路名：.hl-plays-from a.hl-tabs-btn 的 alt
        source_names = []
        m_from = re.search(r'class="[^"]*hl-plays-from[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if m_from:
            for m in re.finditer(r'<a[^>]*class="[^"]*hl-tabs-btn[^"]*"[^>]*alt="([^"]*)"', m_from.group(1)):
                nm = m.group(1).strip()
                if nm:
                    source_names.append(nm)

        # 集数：/anime/{vod_id}/play/{sid}-{nid}.html
        groups = {}
        for m in re.finditer(
                r'href="/anime/%s/play/(\d+)-(\d+)\.html"[^>]*>([^<]{0,30})' % re.escape(str(vod_id)),
                html, re.DOTALL):
            sid, nid, name = m.groups()
            name = self._clean_html(name)
            groups.setdefault(sid, {})[int(nid)] = name

        if not groups:
            return []
        sorted_sids = sorted(groups.keys(), key=lambda s: (min(groups[s].keys()), int(s) if str(s).isdigit() else 0))
        sources = []
        for i, sid in enumerate(sorted_sids):
            eps = sorted(groups[sid].items(), key=lambda x: x[0])
            name = source_names[i] if i < len(source_names) else "线路%s" % sid
            sources.append({
                "source_name": name,
                "episodes": [
                    {"name": n or ("第%d集" % nid), "link": "%s-%s-%s" % (vod_id, sid, nid)}
                    for nid, n in eps
                ],
            })
        return sources

    # ==================== 播放直链解析 ====================
    def _extract_player_data(self, html):
        if not html:
            return None
        m = re.search(r'var\s+player_aaaa\s*=\s*', html)
        if not m:
            return None
        start = m.end()
        while start < len(html) and html[start] != '{':
            start += 1
        if start >= len(html):
            return None
        depth = 1
        i = start + 1
        in_string = False
        escape = False
        while i < len(html) and depth > 0:
            c = html[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
            i += 1
        if depth == 0:
            try:
                return json.loads(html[start:i])
            except Exception:
                pass
        return None

    def _yplayer_decrypt(self, html):
        """解析 Yplayer 页面，AES-CBC 解密出真实地址"""
        enc = re.search(r'encryptedUrl\s*=\s*"([^"]+)"', html)
        key = re.search(r'sessionKey\s*=\s*"([^"]+)"', html)
        if not enc or not key:
            return None
        if not _HAS_AES:
            self._log("缺少 AES 库（pycryptodome），无法解密播放地址")
            return None
        try:
            raw = base64.b64decode(enc.group(1))
            iv, ct = raw[:16], raw[16:]
            cipher = AES.new(key.group(1).encode("utf-8"), AES.MODE_CBC, iv)
            pt = unpad(cipher.decrypt(ct), 16)
            return pt.decode("utf-8").strip()
        except Exception as e:
            self._log("AES 解密失败: %s" % e)
            return None

    def _get_play_url(self, vod_id, sid, nid):
        cache_key = "%s-%s-%s" % (vod_id, sid, nid)
        now = time.time()
        if cache_key in self._play_cache:
            url, ts = self._play_cache[cache_key]
            if now - ts < self._cache_ttl:
                return url

        play_page = "%s/anime/%s/play/%s-%s.html" % (self.base_url, vod_id, sid, nid)
        resp = self._get(play_page, timeout=12)
        html = resp.text if resp else ""
        if not html:
            return play_page
        pd = self._extract_player_data(html)
        if not pd:
            return play_page
        link = (pd.get("url") or "").strip()
        if not link:
            return play_page
        # 第一层：URL 解码得第三方播放页
        third = urllib.parse.unquote(link)
        if not third.startswith("http"):
            third = urllib.parse.unquote(third)
        # 第二层：请求本站播放器，拿 Yplayer 页面并解密
        pr = self._get("%s/player/" % self.base_url, params={"url": third, "next": ""}, timeout=12)
        if pr and pr.text:
            real = self._yplayer_decrypt(pr.text)
            if real:
                self._play_cache[cache_key] = (real, now)
                return real
        # 兜底：返回第三方地址（TVBox 可能无法直接播放，但比空值好）
        self._play_cache[cache_key] = (third, now)
        return third

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = str(id).split("-")
            if len(parts) != 3:
                return {"parse": 0, "url": "", "header": ""}
            vod_id, sid, nid = parts
            play_url = self._get_play_url(vod_id, sid, nid)
            if not play_url:
                play_url = "%s/anime/%s/play/%s-%s.html" % (self.base_url, vod_id, sid, nid)
            is_direct = bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', play_url, re.I))
            self._log("播放URL: %s... parse=%d" % (play_url[:80], 0 if is_direct else 1))
            if is_direct:
                return {"parse": 0, "url": play_url, "header": self.play_headers.copy()}
            # 非直链：交给 TVBox 解析页面
            return {"parse": 1, "url": play_url, "header": ""}
        except Exception as e:
            self._log("playerContent异常: %s" % e)
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
