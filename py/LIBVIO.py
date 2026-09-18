# -*- coding: utf-8 -*-
"""
LIBVIO - libvio.host（LIBVIO 影视站，TVBox 源）

架构说明（已实测验证）：
1. 全站有 PoW（Proof-of-Work）浏览器验证：
   - 首次访问任何路径返回 403 挑战页，内含 TS/SIG/DIFF/MODE 参数
   - 求解 nonce：sha256(SIG + str(i)) 的 hex 前缀匹配 DIFF（如 "0000"）
   - 带 __cdn_pow={TS}_{MODE}_{nonce}_{SIG} 访问 → 302，服务端下发 __cdn_verified（30 分钟有效）
   - 之后所有请求带 Cookie: __cdn_verified=xxx 即可
2. 站点是 MacCMS 10（STUI 模板），页面路径：
   - 首页 /
   - 分类 /type/{tid}.html，分页 /type/{tid}-{page}.html（首页导航 tid：电影1/剧集2/番剧4/日韩15/欧美16）
   - 详情 /detail/{id}.html：vod-info 标题/类型/地区/年份/导演 + 简介 + 豆瓣评分
   - 播放 /w/{id}-{sid}-{nid}.html：player_aaaa={"flag":"play","encrypt":0/3,"url":"..."}
     - encrypt=0/3 时 url 即为播放地址（player.js 无额外解密）
     - 在线线路 url 为 MP4/m3u8 直链；网盘线路 url 为夸克/百度盘分享链接
   - 搜索 /search/{关键词}-------------.html
3. 线路（from 字段）：HD5/vr2/ty 等在线源、kuake/xunlei/uc 网盘源、LINE 系列加密串（过滤）
   加密串线路（url 非 URL 格式）无法在 TVBox 播放，自动过滤。
4. 多域名容错：libvio.host / www.libvio.to / libviobd.com 任一失效自动切换。
"""
import re
import json
import time
import hashlib
import urllib.parse
import urllib.request
import urllib.error
import ssl
import gzip

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
    name = "LIBVIO"
    host = "https://libvio.host"

    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    # 多域名容错（镜像站随时换域名）
    DOMAINS = [
        "https://libvio.host",
        "https://www.libvio.to",
        "https://libviobd.com",
    ]

    # 分类（MacCMS type_id）
    CATEGORIES = [
        ("1", "电影"), ("2", "剧集"), ("4", "番剧"),
        ("15", "日韩"), ("16", "欧美"),
    ]

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    PLAY_HEADERS = {
        "User-Agent": UA,
        "Referer": None,  # 播放时按域名补
    }

    # 网盘域名（playerContent 原样透传，由播放器/解析器决定）
    NETDISK_DOMAINS = ("pan.quark.cn", "pan.baidu.com", "pan.xunlei.com", "pan.uc.cn", "pan.aliyundrive.com")

    def __init__(self, extend=None):
        super().__init__()
        self.extend = extend or ""
        self._session = requests.Session() if requests else None
        if self._session:
            self._session.headers.update({
                "User-Agent": self.UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
        self._base = self.DOMAINS[0]
        self._verified = ""       # __cdn_verified cookie
        self._verified_at = 0
        self._cookie_ttl = 1500   # 25 分钟（服务端 30 分钟有效，留余量）
        self._fail_count = 0
        self._last_req = 0

    # ==================== 工具 ====================
    def _log(self, msg):
        try:
            print("[%s] %s" % (self.name, msg))
        except Exception:
            pass

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r'<[^>]+>', '', s)
        return s.replace("&nbsp;", " ").strip()

    def _min_interval(self):
        """限速：对 PoW 站点友好"""
        now = time.time()
        gap = now - self._last_req
        if gap < 0.6:
            time.sleep(0.6 - gap)
        self._last_req = time.time()

    # ==================== PoW 验证 ====================
    def _solve_challenge(self, base):
        """从挑战页解析参数并求解 nonce，返回 __cdn_verified 或 None"""
        # 1) 拿挑战参数
        t = None
        for _ in range(3):
            st, _, raw = self._raw_request(base + "/")
            if raw:
                t = raw.decode("utf-8", "ignore")
                if 'TS = "' in t:
                    break
                time.sleep(3)
        if not t or 'TS = "' not in t:
            return None
        mts = re.search(r'TS = "(\d+)"', t)
        msig = re.search(r'SIG = "([0-9a-f]+)"', t)
        mdiff = re.search(r'DIFF = "([0-9a-f]+)"', t)
        mmode = re.search(r'MODE = "(\w+)"', t)
        if not (mts and msig and mdiff):
            return None
        ts, sig, diff = mts.group(1), msig.group(1), mdiff.group(1)
        mode = mmode.group(1) if mmode else "auto"

        # 2) 求解 nonce：sha256(SIG + i) 以 DIFF 开头
        nonce = None
        target = diff or "0000"
        for i in range(65536 * 8):
            if hashlib.sha256((sig + str(i)).encode()).hexdigest().startswith(target):
                nonce = i
                break
        if nonce is None:
            return None

        # 3) 带 pow cookie 换 verified cookie
        pow_cookie = "__cdn_pow=%s_%s_%d_%s" % (ts, mode, nonce, sig)
        st, hdrs, _ = self._raw_request(base + "/", cookie=pow_cookie)
        sc = self._get_header(hdrs or {}, "Set-Cookie")
        m = re.search(r'__cdn_verified=([^;]+)', sc)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _get_header(headers, name):
        """大小写不敏感取 header"""
        for k, v in headers.items():
            if str(k).lower() == str(name).lower():
                return v
        return ""

    def _ensure_verified(self):
        """确保持有有效的 verified cookie（带域名切换）"""
        now = time.time()
        if self._verified and (now - self._verified_at) < self._cookie_ttl:
            return True
        self._verified = ""
        for dom in self.DOMAINS:
            c = self._solve_challenge(dom)
            if c:
                self._base = dom
                self._verified = c
                self._verified_at = now
                self._fail_count = 0
                self._log("verified @ %s" % dom)
                return True
            self._log("solve fail @ %s" % dom)
        return False

    # ==================== 网络层（requests -> urllib 双通道） ====================
    def _raw_request(self, url, cookie=None, data=None, timeout=25):
        """低层请求，返回 (status, headers, bytes)。不跟随 302。urllib 优先（requests 被 WAF 识别）。"""
        # urllib
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        h = {"User-Agent": self.UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "zh-CN,zh;q=0.9"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(url, data=data, headers=h)
        opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))
        try:
            resp = opener.open(req, timeout=timeout)
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            return resp.status, dict(resp.headers), raw
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            return e.code, dict(e.headers), raw
        except Exception as e:
            return None, {}, str(e).encode("utf-8", "ignore")

    def _fetch(self, path, timeout=25):
        """带验证 cookie 抓页面；验证失效时自动重解并重试一次。返回 (status, text)"""
        if not self._ensure_verified():
            return None, ""
        url = self._base + path
        self._min_interval()
        st, hdrs, raw = self._raw_request(url, cookie="__cdn_verified=" + self._verified)
        if raw:
            t = raw.decode("utf-8", "ignore")
            # 遇到挑战页 -> 重解
            if '正在验证' in t or 'TS = "' in t:
                self._verified = ""
                if not self._ensure_verified():
                    return None, ""
                self._min_interval()
                st, hdrs, raw = self._raw_request(url, cookie="__cdn_verified=" + self._verified)
                t = raw.decode("utf-8", "ignore") if raw else ""
            return st, t
        return st, ""

    def _fetch_play(self, path):
        """播放页 GET（播放源域名可能不同，允许 Referer 变体）"""
        if not self._ensure_verified():
            return ""
        self._min_interval()
        st, hdrs, raw = self._raw_request(self._base + path, cookie="__cdn_verified=" + self._verified)
        if st == 200 and raw:
            t = raw.decode("utf-8", "ignore")
            if '正在验证' in t:
                self._verified = ""
                if not self._ensure_verified():
                    return ""
                st, hdrs, raw = self._raw_request(self._base + path, cookie="__cdn_verified=" + self._verified)
                t = raw.decode("utf-8", "ignore") if raw else ""
            return t
        return ""

    # ==================== 页面解析 ====================
    _re_vod_card = re.compile(
        r'<a[^>]+href="(/detail/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*(?:data-original="([^"]*)")?[^>]*>'
        r'(?:(?!</a>).)*?<span class="pic-text[^"]*"[^>]*>([^<]*)</span>'
        r'(?:<span class="pic-tag[^"]*"[^>]*>([^<]*)</span>)?', re.S)

    _RE_DETAIL_INFO = re.compile(r'<span class="meta-item">([^<]+)</span>')

    def _parse_list_html(self, t):
        """解析分类/搜索页的影片卡片列表"""
        vods = []
        seen = set()
        # 卡片
        for m in re.finditer(r'<a[^>]+href="(/detail/(\d+)\.html)"[^>]*title="([^"]*)"', t):
            url, vid, title = m.group(1), m.group(2), m.group(3).strip()
            if vid in seen or not title:
                continue
            seen.add(vid)
            # 封面与备注：回查该 href 的卡片块
            block = t[m.start():m.start() + 1200]
            pic = ""
            pm = re.search(r'data-original="([^"]+)"', block)
            if pm:
                pic = pm.group(1)
            remark = ""
            rm = re.search(r'<span class="pic-text[^>]*>([^<]*)</span>', block)
            if rm:
                remark = rm.group(1).strip()
            score = ""
            sm = re.search(r'<span class="pic-tag[^>]*>([^<]*)</span>', block)
            if sm:
                score = sm.group(1).strip()
            remark = remark or score
            vods.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })
            if len(vods) >= 60:
                break
        return vods

    # ==================== TVBox 接口 ====================
    def homeContent(self, filter):
        classes = [{"type_id": cid, "type_name": name} for cid, name in self.CATEGORIES]
        # 首页推荐（电影分类第一页）
        st, html = self._fetch("/type/1.html")
        vods = self._parse_list_html(html) if html else []
        return {"class": classes, "list": vods}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._safe_int(pg, 1)
        path = "/type/%s.html" % tid if pg <= 1 else "/type/%s-%s.html" % (tid, pg)
        st, html = self._fetch(path)
        vods = self._parse_list_html(html) if html else []
        return {
            "list": vods,
            "page": pg,
            "pagecount": pg + 1 if len(vods) >= 20 else pg,
            "limit": 30,
            "total": len(vods),
        }

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        st, html = self._fetch("/detail/%s.html" % vid)
        if not html:
            return {"list": []}

        title = ""
        tm = re.search(r'<h1[^>]*class="title"[^>]*>([^<]+)</h1>', html)
        if tm:
            title = tm.group(1).strip()

        # 封面
        pic = ""
        pm = re.search(r'<img class="lazyload"\s+data-original="([^"]+)"', html)
        if pm:
            pic = pm.group(1)
        if not pic:
            pm2 = re.search(r'data-original="([^"]+)"[^>]*>\s*</a>\s*</div>\s*</div>\s*<div class="stui-content__detail"', html)
            if pm2:
                pic = pm2.group(1)

        # 类型/地区/年份/集数
        meta_items = []
        for m in self._RE_DETAIL_INFO.finditer(html):
            v = m.group(1).strip()
            if v and "：" not in v and ":" not in v:
                meta_items.append(v)
        type_name = meta_items[0] if meta_items else ""
        area = meta_items[1] if len(meta_items) > 1 else ""
        year = meta_items[2] if len(meta_items) > 2 else ""

        # 导演
        director = ""
        dm = re.search(r'<span class="meta-item">导演[：:]([^<]+)</span>', html)
        if dm:
            director = dm.group(1).strip()
        # 主演
        actor = ""
        am = re.search(r'<span class="meta-item">主演[：:]([^<]+)</span>', html)
        if am:
            actor = am.group(1).strip()

        # 简介
        desc = ""
        dm2 = re.search(r'<span class="detail-sketch">([^<]*)</span>', html)
        if dm2:
            desc = dm2.group(1).strip()
        if not desc:
            dm3 = re.search(r'<span class="detail-content"[^>]*>([^<]*)</span>', html)
            if dm3:
                desc = dm3.group(1).strip()

        # 线路 + 集数：playlist-panel 分段解析（panel 内 div 嵌套，finditer 非贪婪会截断）
        lines = []  # [(线路名, [(集名, sid, nid)])]
        for seg in re.split(r'<div class="playlist-panel[^"]*">', html)[1:]:
            hm = re.search(r'<h3>([^<]+)</h3>', seg)
            line_name = hm.group(1).strip() if hm else "线路"
            eps = []
            for em in re.finditer(r'href="/w/\d+-(\d+)-(\d+)\.html"[^>]*>([^<]+)</a>', seg):
                eps.append((em.group(3).strip(), em.group(1), em.group(2)))
            if eps:
                lines.append((line_name, eps))

        # 组装播放地址（过滤：url 必须是 http(s)，保留网盘线路但不优先）
        play_from = []
        play_urls = []
        for line_name, eps in lines:
            if not eps:
                continue
            parts = []
            for ep_title, sid, nid in eps:
                parts.append("%s$%s" % (ep_title, "%s|%s|%s" % (vid, sid, nid)))
            play_from.append(line_name)
            play_urls.append("#".join(parts))

        if not play_urls:
            return {"list": [{
                "vod_id": vid,
                "vod_name": title or vid,
                "vod_pic": pic,
                "vod_content": desc,
                "vod_play_from": "",
                "vod_play_url": "",
            }]}

        vod = {
            "vod_id": vid,
            "vod_name": title or vid,
            "vod_pic": pic,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_director": director,
            "vod_actor": actor,
            "vod_content": desc,
            "vod_remarks": meta_items[-1] if meta_items else "",
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_urls),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg):
        pg = self._safe_int(pg, 1)
        if pg > 5:
            return {"list": []}
        kw = urllib.parse.quote(key)
        st, html = self._fetch("/search/%s-------------.html" % kw)
        vods = self._parse_list_html(html) if html else []
        return {
            "list": vods,
            "page": pg,
            "pagecount": 1,
            "limit": 30,
            "total": len(vods),
        }

    def playerContent(self, flag, id, vipFlags):
        # id 格式: {vodid}|{sid}|{nid}
        parts = id.split("|")
        if len(parts) != 3:
            return {"parse": 0, "url": ""}
        vid, sid, nid = parts[0], parts[1], parts[2]
        path = "/w/%s-%s-%s.html" % (vid, sid, nid)
        html = self._fetch_play(path)
        if not html:
            return {"parse": 0, "url": ""}
        m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if not m:
            return {"parse": 0, "url": ""}
        try:
            j = json.loads(m.group(1))
        except Exception:
            return {"parse": 0, "url": ""}
        url = j.get("url") or ""
        if not url or not re.match(r'^https?://', url):
            # 加密串/网盘链接：无 URL 直接返回空
            if url:
                self._log("线路 %s 非直链 url: %s..." % (flag, url[:40]))
            return {"parse": 0, "url": ""}
        header = {
            "User-Agent": self.UA,
            "Referer": self._base + "/",
        }
        return {"parse": 0, "playUrl": "", "url": url, "header": header}

    # ==================== 入口 ====================
    @staticmethod
    def _safe_int(v, default=1):
        try:
            return int(float(v))
        except Exception:
            return default

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


if __name__ == "__main__":
    s = Spider()
    r = s.searchContent("超人和露易丝", False, 1)
    print("搜索:", len(r.get("list") or []))
    for v in (r.get("list") or [])[:3]:
        print("  ", v["vod_id"], v["vod_name"], v.get("vod_remarks"))
    if r.get("list"):
        d = s.detailContent([r["list"][0]["vod_id"]])
        v = (d.get("list") or [{}])[0]
        print("详情:", v.get("vod_name"), "| 线路:", str(v.get("vod_play_from"))[:60])
        u = (v.get("vod_play_url") or "").split("$$$")
        if u and u[0]:
            first_ep = u[0].split("#")[0]
            ep_name, _, ep_id = first_ep.partition("$")
            parts = ep_id.split("|")
            print("首集:", ep_name, parts)
            if len(parts) == 3:
                p = s.playerContent("在线", ep_id, "")
                print("播放:", str(p.get("url"))[:100])