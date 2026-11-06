# -*- coding: utf-8 -*-
# 黄果短剧 融合版（国内直连优化）
# 改动重点：
#   - 启动时自动从官方发布页拉取最新免翻墙线路
#   - 优先使用国内可直连子域名（*.dsqqahhno.cc / *.arj2ftl0.cc 等）
#   - 主站 huangguoai.com 放到最后兜底
#   - 其余功能（分类API、AES封面、本地代理、播放直链）保持不变
# 依赖：requests, beautifulsoup4, pycryptodome (或 Crypto)
# 适配 TVBox / 类 TVBox 壳

import sys
import re
import json
import time
import base64
import random
import string
import threading
import html as htmllib
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass

try:
    import requests as rq
    rq.packages.urllib3.disable_warnings()
except Exception:
    pass

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None

# ---------- 常量 ----------

# 国内友好的泛域名后缀（官方常用，含新线路）
_DOMESTIC_SUFFIXES = [
    "lbvrhyir.cc",
    "cewfmcve.cc",
    "dsqqahhno.cc",
    "arj2ftl0.cc",
    "jxqgmx5ga.cc",
    "40ygo615.cc",
    "ediayikma.cc",
    "ye28r31s.cc",
    "cm06z19q.cc",
]

# 官方发布页（用于自动获取最新直连地址）
_PUBLISH_PAGES = [
    "https://huangguoai.ai/",
    "https://huangguoai.com/go-home/",
    "https://huangguoai.pages.dev/",
    "https://hgai11.com/",
    "https://hgai10.com/",
    "https://hgai9.com/",
]

def _gen_random_subdomain():
    """生成 3-6 位随机小写字母数字子域名"""
    length = random.randint(3, 6)
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def _gen_backup_hosts(n=10):
    """生成国内友好的随机泛域名备用"""
    hosts = []
    for _ in range(n):
        suffix = random.choice(_DOMESTIC_SUFFIXES)
        hosts.append(f"https://{_gen_random_subdomain()}.{suffix}")
    return hosts


# 初始 HOSTS：主站放最后，前面放已知可用的国内线路 + 随机生成
# 实际运行时会在 init 里用官方发布页覆盖/补充
HOSTS = [
    "https://bgq1.lbvrhyir.cc",
    "https://p8ojg7.lbvrhyir.cc",
    "https://mi6wos.lbvrhyir.cc",
    "https://xeltc.lbvrhyir.cc",
    "https://hitt4e.lbvrhyir.cc",
    "https://lxiwi.lbvrhyir.cc",
    "https://h9s5.dsqqahhno.cc",
    "https://y4vw.dsqqahhno.cc",
    "https://zfprv.dsqqahhno.cc",
] + _gen_backup_hosts(6) + ["https://huangguoai.com"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 18
PAGE_SIZE = 24
# AES 封面解密（站点 CDN 加密）
_AES_KEY = b'f5d965df75336270'
_AES_IV = b'97b60394abc2fbe1'
_PLACEHOLDER_GIF = base64.b64decode(
    'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
_PROXY_PORT = [0]
_TAG_RE = re.compile(r'<[^>]+>')
_LABEL_RE = re.compile(r'<[^>]+>')

_BS4_PARSER = None
if BeautifulSoup is not None:
    try:
        BeautifulSoup("<a/>", "lxml")
        _BS4_PARSER = "lxml"
    except Exception:
        _BS4_PARSER = "html.parser"


def _clean(s):
    if not s:
        return ""
    s = htmllib.unescape(str(s))
    s = _TAG_RE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# ---------- 本地图片代理服务器 ----------
try:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    def _fetch_img_raw(u, referer):
        headers = {"User-Agent": UA, "Referer": referer,
                   "Accept": "image/*"}
        try:
            rr = rq.get(u, headers=headers, timeout=15, verify=False,
                        allow_redirects=True)
            if rr.status_code == 200 and rr.content and len(rr.content) > 50:
                return rr.content
        except Exception:
            pass
        return b''

    def _decrypt_img(data):
        if not data or AES is None:
            return data
        if data[:3] == b'\xff\xd8\xff' or data[:8] == b'\x89PNG\r\n\x1a\n' \
                or data[:6] in (b'GIF87a', b'GIF89a') \
                or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
            return data
        try:
            dec = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(data)
            pad = dec[-1]
            if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]):
                dec = dec[:-pad]
            else:
                dec = dec.rstrip(b'\x00')
            if dec[:3] == b'\xff\xd8\xff' or dec[:8] == b'\x89PNG\r\n\x1a\n':
                return dec
            return dec
        except Exception:
            return data

    def _detect_mime(data):
        if data[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image/webp'
        return 'image/jpeg'

    class _ImgHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                pr = urllib.parse.urlparse(self.path)
                if pr.path not in ('/img', '/proxy'):
                    self.send_response(404)
                    self.end_headers()
                    return
                q = urllib.parse.parse_qs(pr.query)
                u = q.get('u', q.get('url', ['']))[0]
                u = urllib.parse.unquote(u)
                if not u.startswith('http'):
                    self.send_response(400)
                    self.end_headers()
                    return
                raw = _fetch_img_raw(u, HOSTS[0] + "/")
                data = _decrypt_img(raw) if raw else b''
                if not data or len(data) < 50:
                    data, ctype = _PLACEHOLDER_GIF, 'image/gif'
                else:
                    ctype = _detect_mime(data)
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                pass

        def log_message(self, *args):
            pass

    def _start_proxy_server():
        if _PROXY_PORT[0]:
            return _PROXY_PORT[0]
        for port in [9978] + list(range(9979, 10020)) + list(range(30261, 30281)):
            try:
                srv = HTTPServer(('127.0.0.1', port), _ImgHandler)
                _PROXY_PORT[0] = port
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                return port
            except Exception:
                continue
        return 0
except Exception:
    def _start_proxy_server():
        return 0
    def _decrypt_img(data):
        return data
    def _detect_mime(data):
        return 'image/jpeg'


class Spider(Spider):

    _PRIMARY_FAIL_THRESHOLD = 2   # 国内线路失败阈值更低，更快切换

    def getName(self):
        return "黄果短剧"

    def init(self, extend=""):
        # 先用预置的国内线路，不阻塞
        self.host = HOSTS[0].rstrip('/')
        self._working_backups = []
        self._primary_fails = [0]
        self._list_cache = {}

        try:
            self.s = rq.Session()
            self.s.verify = False
            self.s.headers.update({
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": self.host + "/",
            })
            try:
                from requests.adapters import HTTPAdapter
                _adapter = HTTPAdapter(
                    pool_connections=16, pool_maxsize=32, max_retries=0)
                self.s.mount('http://', _adapter)
                self.s.mount('https://', _adapter)
            except Exception:
                pass
        except Exception:
            self.s = None

        try:
            _start_proxy_server()
        except Exception:
            pass

        # 后台：1) 从官方发布页拉取最新线路  2) 探测所有候选
        try:
            t = threading.Thread(target=self._bootstrap_hosts, daemon=True)
            t.start()
        except Exception:
            pass

    def _extract_hosts_from_text(self, text):
        """从发布页文本里提取 https://xxx.yyy.cc 形式的地址"""
        if not text:
            return []
        # 已知国内后缀 + 任意 *.xxx.cc 短子域名（含无线路 lbvrhyir / cewfmcve 等）
        found = re.findall(
            r'(?:https?://)?([a-z0-9]{2,15}\.(?:lbvrhyir|cewfmcve|dsqqahhno|arj2ftl0|jxqgmx5ga|40ygo615|ediayikma|ye28r31s|cm06z19q)\.cc)',
            text, re.I)
        found2 = re.findall(
            r'(?:https?://)?([a-z0-9]{2,12}\.[a-z0-9]{5,18}\.cc)',
            text, re.I)
        hosts = []
        seen = set()
        for h in found + found2:
            h = h.lower().rstrip('/')
            if h not in seen and not h.startswith('www.') and 'huangguo' not in h:
                seen.add(h)
                hosts.append("https://" + h)
        return hosts

    def _fetch_publish_hosts(self):
        """并行请求官方发布页，提取最新国内线路"""
        results = []
        lock = threading.Lock()

        def _one(url):
            try:
                r = rq.get(url, headers={"User-Agent": UA}, timeout=6, verify=False)
                if r.status_code == 200 and r.text:
                    hs = self._extract_hosts_from_text(r.text)
                    with lock:
                        results.extend(hs)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(_one, _PUBLISH_PAGES))
        # 去重保序
        seen = set()
        uniq = []
        for h in results:
            if h not in seen:
                seen.add(h)
                uniq.append(h)
        return uniq

    def _bootstrap_hosts(self):
        """后台启动：拉取最新发布页 + 探测可用性"""
        try:
            fresh = self._fetch_publish_hosts()
        except Exception:
            fresh = []

        # 合并：发布页最新 + 预置 + 随机生成，主站最后
        candidates = []
        seen = set()
        for h in fresh + HOSTS:
            h = h.rstrip('/')
            if h and h not in seen:
                seen.add(h)
                candidates.append(h)

        # 并行探测，收集可用
        good = []
        lock = threading.Lock()

        def _probe(h):
            r = self._probe_host(h)
            if r:
                with lock:
                    good.append(r)

        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as ex:
            list(ex.map(_probe, candidates[:20]))  # 最多探20个

        if good:
            self._working_backups = good
            # 把第一个可用的切成当前 host
            if good[0] != self.host:
                self._switch_host(good[0])

    @staticmethod
    def _probe_host(h):
        """单机探测：返回可用 host，否则 None"""
        try:
            r = rq.get(h.rstrip('/'), headers={"User-Agent": UA}, timeout=4, verify=False)
            if r.status_code == 200 and (
                    '黄果' in r.text or 'huangguo' in r.text.lower()
                    or len(r.text) > 2000):
                return h.rstrip('/')
        except Exception:
            pass
        return None

    def _switch_host(self, new_host):
        new_host = (new_host or "").rstrip('/')
        if not new_host:
            return
        self.host = new_host
        try:
            if self.s is not None:
                self.s.headers["Referer"] = new_host + "/"
        except Exception:
            pass

    def _fetch_one(self, host, path, ref, timeout):
        url = host + path
        try:
            headers = {"Referer": host + ref}
            r = rq.get(url, timeout=timeout, verify=False, allow_redirects=True,
                       headers={"User-Agent": UA,
                                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                "Accept-Language": "zh-CN,zh;q=0.9",
                                **headers})
            if r.status_code == 200 and r.text:
                r.encoding = 'utf-8'
                return r.text
        except Exception:
            pass
        return ""

    def _wrap_pic(self, url):
        if not url or not str(url).startswith('http'):
            return url or ""
        if not _PROXY_PORT[0]:
            _start_proxy_server()
        if _PROXY_PORT[0]:
            return ("http://127.0.0.1:%d/proxy?url=%s"
                    % (_PROXY_PORT[0], urllib.parse.quote(url, safe='')))
        try:
            b = base64.b64encode(url.encode('utf-8')).decode('ascii')
            return f"proxy://type=pic&url={b}"
        except Exception:
            return url

    def _get(self, path, ref="/"):
        if path.startswith("http"):
            try:
                headers = {"Referer": self.host.rstrip('/') + ref}
                if self.s is not None:
                    r = self.s.get(path, timeout=TIMEOUT, allow_redirects=True, headers=headers)
                else:
                    r = rq.get(path, timeout=TIMEOUT, verify=False,
                               headers={"User-Agent": UA, **headers})
                if r.status_code == 200 and r.text:
                    r.encoding = 'utf-8'
                    return r.text
            except Exception:
                pass
            return ""

        current = getattr(self, 'host', HOSTS[0]).rstrip('/')

        # 1) 当前 host
        try:
            url = current + path
            headers = {"Referer": current + ref}
            if self.s is not None:
                r = self.s.get(url, timeout=8, allow_redirects=True, headers=headers)
            else:
                r = rq.get(url, timeout=8, verify=False,
                           headers={"User-Agent": UA, **headers})
            if r.status_code == 200 and r.text:
                r.encoding = 'utf-8'
                try:
                    self._primary_fails[0] = 0
                except (AttributeError, IndexError):
                    pass
                return r.text
        except Exception:
            pass

        # 2) 累计失败，达到阈值切到下一个可用
        try:
            self._primary_fails[0] += 1
            if (self._primary_fails[0] >= self._PRIMARY_FAIL_THRESHOLD
                    and getattr(self, '_working_backups', None)):
                # 找下一个不是 current 的
                for h in self._working_backups:
                    if h != current:
                        self._switch_host(h)
                        break
        except (AttributeError, IndexError):
            pass

        # 3) 并行试预热好的备用
        try:
            known_good = list(getattr(self, '_working_backups', None) or [])
        except Exception:
            known_good = []
        candidates = [h for h in known_good if h != current][:5]

        if not candidates:
            all_hosts = [h.rstrip('/') for h in HOSTS if h.rstrip('/') != current]
            candidates = all_hosts[:5]

        if not candidates:
            return ""

        with ThreadPoolExecutor(max_workers=len(candidates)) as ex:
            futs = {ex.submit(self._fetch_one, h, path, ref, 6): h for h in candidates}
            try:
                for fut in as_completed(futs, timeout=8):
                    try:
                        text = fut.result()
                        if text:
                            for f in futs:
                                f.cancel()
                            won = futs[fut]
                            self._switch_host(won)
                            return text
                    except Exception:
                        continue
            except Exception:
                pass
        return ""

    def _get_cached(self, path, ref="/", ttl=60):
        try:
            cache = self._list_cache
        except AttributeError:
            cache = self._list_cache = {}
        key = path
        now = time.time()
        cached = cache.get(key)
        if cached and now - cached[1] < ttl:
            return cached[0]
        text = self._get(path, ref)
        if text:
            cache[key] = (text, now)
            if len(cache) > 80:
                for k in list(cache.keys()):
                    if now - cache[k][1] > ttl:
                        cache.pop(k, None)
        return text

    def isVideoFormat(self, url):
        return any(x in (url or '') for x in ['.m3u8', '.mp4', '.flv', '.mkv', '.avi'])

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": "recommend", "type_name": "精选推荐"},
                {"type_id": "newest", "type_name": "最近上新"},
                {"type_id": "ai-duanju", "type_name": "AI成人短剧"},
                {"type_id": "ai-manju", "type_name": "AI成人漫剧"},
                {"type_id": "ai-huanlian", "type_name": "AI换脸"},
                {"type_id": "ai-mogai", "type_name": "AI魔改"},
                {"type_id": "topic", "type_name": "📌专题"},
                {"type_id": "ranks", "type_name": "排行榜"},
                {"type_id": "chigua", "type_name": "黄果吃瓜"},
                {"type_id": "author", "type_name": "黄果官方"},
            ],
            "list": [],
            "filters": {
                "ranks": [{"key": "类型", "name": "类型", "value": [
                    {"n": "热播榜", "v": "hot"},
                    {"n": "推荐榜", "v": "recommend"},
                    {"n": "潜力榜", "v": "potential"},
                ]}],
                "chigua": [{"key": "类型", "name": "类型", "value": [
                    {"n": "全部", "v": "page"},
                    {"n": "热门吃瓜", "v": "remen"},
                    {"n": "AI原创", "v": "yuanchuang"},
                ]}],
                "author": [{"key": "类型", "name": "类型", "value": [
                    {"n": "黄果官方", "v": "156291"},
                    {"n": "黄果ai大师", "v": "156305"},
                ]}],
            }
        }
        if filter:
            pass
        try:
            # 优先 API，避免首页 HTML 结构变动导致空列表
            videos, _, _ = self._list_api("hot", 1)
            if videos:
                result["list"] = videos
            else:
                html = self._get_cached("/")
                if html:
                    result["list"] = self._parse_list(html)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            videos, _, _ = self._list_api("hot", 1)
            if videos:
                return {"list": videos}
            html = self._get_cached("/recommend/")
            if not html:
                html = self._get_cached("/")
            return {"list": self._parse_list(html)}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pg = int(str(pg or 1))
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        cid = str(tid or "").strip().strip("/")
        ext = extend if isinstance(extend, dict) else {}
        rc = ext.get("类型", cid)

        videos, pages, total = [], 9999, 0

        try:
            if cid.startswith("dir_topic_"):
                slug = cid.replace("dir_topic_", "")
                html = self._get_cached(f"/topics/{slug}/?page={pg}")
                videos = self._parse_list(html, mode="drama")
                return self._result(videos, pg, 9999)

            if cid in ("ai-duanju", "ai-manju", "ai-huanlian", "ai-mogai"):
                videos, pages, total = self._category_api(cid, pg)
                if not videos:
                    path = f"/{cid}/" if pg <= 1 else f"/{cid}/{pg}/"
                    html = self._get_cached(path)
                    videos = self._parse_list(html)
                    ps = [int(x) for x in re.findall(
                        r'/' + re.escape(cid) + r'/(\d+)/', html or "")]
                    if ps:
                        pages = max(ps)
                if len(videos) > PAGE_SIZE:
                    videos = videos[:PAGE_SIZE]
                return self._result(videos, pg, pages or 9999, total)

            if cid == "recommend":
                # 精选推荐：API sort=hot（推荐/热播）
                videos, pages, total = self._list_api("hot", pg)
                if not videos:
                    path = f"/recommend/{pg}/" if pg > 1 else "/recommend/"
                    html = self._get_cached(path)
                    videos = self._parse_list(html)
            elif cid == "newest":
                # 最近上新：API sort=new
                videos, pages, total = self._list_api("new", pg)
                if not videos:
                    path = f"/newest/{pg}/" if pg > 1 else "/newest/"
                    html = self._get_cached(path)
                    videos = self._parse_list(html)
            elif cid == "topic":
                html = self._get_cached("/topics/")
                videos = self._parse_list(html, mode="topic")
                pages = 1
            elif cid == "ranks":
                rtype = rc if rc in ("hot", "recommend", "potential") else "hot"
                html = self._get_cached(f"/ranks/{rtype}/")
                videos = self._parse_list(html, mode="rank")
                pages = 1
            elif cid == "chigua":
                ctype = rc if rc in ("page", "remen", "yuanchuang") else "page"
                html = self._get_cached(f"/chigua/{ctype}/{pg}/")
                videos = self._parse_list(html, mode="post")
            elif cid == "author":
                aid = rc if str(rc).isdigit() else "156291"
                html = self._get(f"/author/{aid}/video/{pg}/")
                videos = self._parse_list(html)
            else:
                path = f"/{cid}/" if pg <= 1 else f"/{cid}/{pg}/"
                html = self._get(path)
                videos = self._parse_list(html)

        except Exception:
            videos = []

        return self._result(videos, pg, pages, total)

    def _category_api(self, slug, pg):
        url = (f"/api/videos/category/{urllib.parse.quote(slug)}"
               f"?sort=hot&page={pg}&size={PAGE_SIZE}")
        text = self._get_cached(url, ref="/" + slug + "/")
        if not text:
            return [], 0, 0
        try:
            data = json.loads(text)
        except Exception:
            return [], 0, 0
        d = data.get("data") or {}
        items = d.get("items") or []
        pag = d.get("pagination") or {}
        videos = []
        for it in items:
            v = self._api_item(it)
            if v:
                videos.append(v)
        pages = total = 0
        try:
            pages = int(pag.get("pages") or 0)
        except Exception:
            pass
        try:
            total = int(pag.get("total") or 0)
        except Exception:
            pass
        return videos, pages, total

    def _list_api(self, sort, pg):
        """通用列表 API：/api/videos?sort=hot|new&page=&size=
        用于精选推荐(hot)、最近上新(new)，比 HTML 解析更稳定。
        """
        sort = (sort or "hot").strip()
        if sort not in ("hot", "new", "recommend", "newest"):
            sort = "hot"
        if sort == "recommend":
            sort = "hot"
        if sort == "newest":
            sort = "new"
        url = f"/api/videos?sort={sort}&page={pg}&size={PAGE_SIZE}"
        text = self._get_cached(url, ref="/")
        if not text:
            return [], 0, 0
        try:
            data = json.loads(text)
        except Exception:
            return [], 0, 0
        d = data.get("data") or {}
        items = d.get("items") or []
        pag = d.get("pagination") or {}
        videos = []
        for it in items:
            v = self._api_item(it)
            if v:
                videos.append(v)
        pages = total = 0
        try:
            pages = int(pag.get("pages") or 0)
        except Exception:
            pass
        try:
            total = int(pag.get("total") or 0)
        except Exception:
            pass
        return videos, pages, total

    def _api_item(self, it):
        vid = it.get("id")
        if vid is None:
            return None
        title = _clean(it.get("title"))
        if not title:
            return None
        pic = (it.get("cover") or "").strip()
        # 相对路径补全为绝对地址
        if pic and pic.startswith("/"):
            pic = (getattr(self, "host", "") or HOSTS[0]).rstrip("/") + pic
        epc = it.get("episode_count")
        finished = it.get("is_finished")
        if finished:
            remark = "全%d集" % epc if epc else "全剧"
        else:
            remark = "更新至%d集" % epc if epc else "连载中"
        score = it.get("score")
        if score:
            remark = f"{score}分 " + remark
        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": self._wrap_pic(pic),
            "vod_remarks": remark or "在线观看",
        }

    def _result(self, videos, pg, pagecount=9999, total=0):
        n = len(videos)
        if total < 1:
            total = pagecount * max(n, 1) if pagecount > 1 else n
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": total,
        }

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, page):
        kw = urllib.parse.quote(str(key or "").strip())
        if not kw:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(page) if page else 1
        except Exception:
            pg = 1
        html = self._get(f"/search/video/{kw}/{pg}/")
        videos = self._parse_list(html, mode="search")
        has_more = len(videos) >= 18
        return {
            "page": pg,
            "pagecount": pg + 1 if has_more else pg,
            "limit": 20,
            "total": 0,
            "list": videos,
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            raw = ids[0] if isinstance(ids, (list, tuple)) else ids
            did = str(raw).strip()
        except Exception:
            return {"list": []}
        if not did:
            return {"list": []}

        if "/archives/" in did or did.startswith("http") and "archives" in did:
            return self._detail_chigua(did)

        m = re.search(r'(?:detail/|/)?(\d+)/?$', did)
        vid = m.group(1) if m else (did if did.isdigit() else None)
        vhtml = ""
        if vid:
            primary = self.host.rstrip('/')
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut_video = ex.submit(self._fetch_one, primary,
                                      f"/video/{vid}/", "/", 10)
                html = self._get(f"/detail/{vid}/")
                vhtml = fut_video.result()
        else:
            html = self._get(did if did.startswith("/") else "/" + did)

        if not html:
            return {"list": []}

        title = ""
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            title = _clean(m.group(1))
        if not title:
            m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if m:
                title = _clean(m.group(1))
        if not title:
            m = re.search(r'<title>(.*?)</title>', html)
            if m:
                title = _clean(m.group(1).split('|')[0])
        if not title:
            return {"list": []}

        pic = ""
        m = re.search(r'<img[^>]*data-src="([^"]+)"[^>]*>', html)
        if m:
            pic = htmllib.unescape(m.group(1)).strip()
        if not pic:
            m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if m:
                pic = htmllib.unescape(m.group(1)).strip()

        desc = ""
        m = re.search(r'<p class="[^"]*hg-web-detail__desc[^"]*"[^>]*>(.*?)</p>', html, re.S)
        if m:
            desc = _clean(m.group(1))
        if not desc:
            m = re.search(r'<meta name="description" content="([^"]+)"', html)
            if m:
                desc = _clean(m.group(1))

        meta = ""
        m = re.search(r'class="[^"]*hg-web-detail__meta[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if m:
            meta = _clean(m.group(1))
        tags = []
        for m in re.finditer(r'class="hg-tag"[^>]*href="(/tag/[^"]+)"[^>]*>([^<]+)<', html):
            tags.append(_clean(m.group(2)))
        remark = meta or "在线观看"

        eps = []
        seen = set()
        ep_re = (r'href="(/video/' + re.escape(vid)
                 + r'/[^"]*?)"[^>]*>(.*?)</a>')
        _ep_num_re = re.compile(r'/(?:ep-?|episode-?|p|play-?)(\d+)/?', re.I)
        _fallback_seq = [0]

        def _label_from_path(path):
            m = _ep_num_re.search(path or "")
            if m:
                return "%02d" % int(m.group(1))
            _fallback_seq[0] += 1
            return "%02d" % _fallback_seq[0]

        if vid:
            for m in re.finditer(ep_re, html, re.S):
                path = m.group(1)
                if not path.startswith("/video/"):
                    continue
                if path in seen:
                    continue
                label = _label_from_path(path)
                seen.add(path)
                eps.append((label, path))
            if not eps:
                for m in re.finditer(ep_re, vhtml or "", re.S):
                    path = m.group(1)
                    if not path.startswith("/video/") or path in seen:
                        continue
                    label = _label_from_path(path)
                    seen.add(path)
                    eps.append((label, path))
                if not eps and vhtml:
                    for m in re.finditer(
                            r'<a[^>]*class="hg-play__ep-item[^"]*"[^>]*href="([^"]*)"[^>]*data-ep-id="([^"]*)"[^>]*>(.*?)</a>',
                            vhtml, re.S):
                        path = m.group(1)
                        ep_id = m.group(2)
                        label = _label_from_path(path)
                        if ep_id and ep_id.isdigit() and label.startswith("0") and not _ep_num_re.search(path or ""):
                            label = "%02d" % int(ep_id)
                        if not path.startswith('/'):
                            path = '/' + path
                        if path not in seen:
                            seen.add(path)
                            eps.append((label, path))

        eps = sorted(eps, key=lambda x: self._ep_sort(x[1]))
        if not eps and vid:
            eps = [("01", f"/video/{vid}/")]

        play_from = ["正片"]
        play_url = ["#".join(f"{l}${p}" for l, p in eps)]

        vod = {
            "vod_id": vid or did,
            "vod_name": title,
            "vod_pic": self._wrap_pic(pic),
            "type_name": ",".join(tags) or "黄果短剧",
            "vod_remarks": remark,
            "vod_content": desc,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
            "vod_year": "",
            "vod_area": "",
            "vod_actor": "",
            "vod_director": "",
        }
        return {"list": [vod]}

    def _detail_chigua(self, url):
        if not url.startswith("http"):
            url = self.host.rstrip('/') + (url if url.startswith('/') else '/' + url)
        try:
            html = self._get(url.replace(self.host, "")) if url.startswith(self.host) else ""
            if not html:
                r = rq.get(url, headers={"User-Agent": UA, "Referer": self.host + "/"},
                           timeout=TIMEOUT, verify=False)
                html = r.text if r.status_code == 200 else ""
        except Exception:
            return {"list": []}
        if not html:
            return {"list": []}

        title = ""
        m = re.search(r'<title>(.*?)</title>', html)
        if m:
            title = _clean(m.group(1).split('|')[0])

        players = re.findall(
            r'<div class="post-video-player"[^>]*data-player-key="([^"]*)"[^>]*data-src="([^"]*)"', html)
        if not players:
            players = re.findall(r'data-src="(https?://[^"]+\.m3u8[^"]*)"', html)
            players = [(f"线路{i+1}", u) for i, u in enumerate(players)]

        play = "#".join([f"{k}${v.replace('&amp;', '&')}" for k, v in players]) if players else ""

        video = {
            "vod_id": url,
            "vod_name": title or "吃瓜",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": title,
            "type_name": "黄果吃瓜",
            "vod_play_from": "黄果吃瓜",
            "vod_play_url": play or f"正片${url}",
            "vod_year": "", "vod_area": "", "vod_actor": "", "vod_director": "",
        }
        return {"list": [video]}

    @staticmethod
    def _ep_sort(path):
        m = re.search(r'/(?:ep-?|episode-?|p|play-?)(\d+)/?', path or "", re.I)
        return int(m.group(1)) if m else 0

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None, vipIds=None):
        key = str(id or "").strip()
        if not key:
            return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

        def _norm(u):
            if not u:
                return ""
            u = str(u).replace("\\u0026", "&").replace("&amp;", "&").strip()
            if u.startswith("//"):
                u = "https:" + u
            return u

        def _direct(url):
            url = _norm(url)
            if not url:
                return ""
            if url.startswith("http") and self.isVideoFormat(url):
                return url
            if url.startswith("http") and any(
                    x in url for x in ['auth_key', 'playlist.m3u8', '/m3u8/', '.m3u8']):
                return url
            return ""

        if key.startswith("http"):
            u = _direct(key)
            if u:
                return {
                    "parse": 0,
                    "url": u,
                    "header": {"User-Agent": UA, "Referer": self.host + "/"},
                }

        if flag == "黄果吃瓜" and key.startswith("http"):
            return {
                "parse": 0,
                "url": _norm(key),
                "header": {"User-Agent": UA, "Referer": self.host + "/"},
            }

        if key.isdigit():
            key = f"/video/{key}/"
        elif not key.startswith("/") and not key.startswith("http"):
            key = "/" + key

        html = self._get(key, ref="/")
        if not html:
            return {
                "parse": 1,
                "url": self.host.rstrip('/') + key,
                "header": {"User-Agent": UA, "Referer": self.host + "/"},
            }

        m = re.search(
            r'<script id="videoInitialData" type="application/json">(.*?)</script>',
            html, re.S)
        if m:
            try:
                raw = m.group(1)
                data = None
                try:
                    data = json.loads(raw)
                except Exception:
                    for end in range(len(raw), max(0, len(raw) - 2000), -1):
                        try:
                            data = json.loads(raw[:end])
                            break
                        except Exception:
                            continue
                if data:
                    url = ""
                    for k in ("videoSrc", "videoUrl", "playUrl", "src",
                              "url", "video_src", "play_url"):
                        v = data.get(k)
                        if v and isinstance(v, str):
                            url = v
                            break
                    if not url:
                        eps = None
                        for k in ("epPlaySrcs", "episodes", "playSrcs",
                                  "ep_play_srcs", "playSources"):
                            v = data.get(k)
                            if isinstance(v, dict):
                                eps = v
                                break
                        if eps:
                            ep = data.get("ep") or data.get("episode") or data.get("currentEp")
                            if ep is not None and str(ep) in eps:
                                url = eps[str(ep)]
                            else:
                                for ek, ev in eps.items():
                                    if str(ep) in str(ek):
                                        url = ev
                                        break
                                if not url:
                                    for ev in eps.values():
                                        if ev:
                                            url = ev
                                            break
                    url = _norm(url)
                    if url.startswith("http"):
                        return {
                            "parse": 0,
                            "url": url,
                            "header": {"User-Agent": UA, "Referer": self.host + "/"},
                        }
            except Exception:
                pass

        m = re.search(
            r'<article[^>]*class="[^"]*hg-play__slide[^"]*is-active[^"]*"[^>]*data-play-src="([^"]*)"',
            html)
        if not m:
            m = re.search(r'data-play-src="(https?://[^"]+)"', html)
        if m:
            url = _norm(m.group(1))
            if url.startswith("http"):
                return {
                    "parse": 0,
                    "url": url,
                    "header": {"User-Agent": UA, "Referer": self.host + "/"},
                }

        return {
            "parse": 1,
            "url": self.host.rstrip('/') + key,
            "header": {"User-Agent": UA, "Referer": self.host + "/"},
        }

    # ---------- 本地代理（TVBox 调用） ----------
    def localProxy(self, param):
        try:
            if isinstance(param, dict):
                if param.get("type") == "pic":
                    return self._proxy_pic(param)
                url = param.get("url") or param.get("u") or ""
            else:
                url = self._resolve_img_param(param)
            if not url:
                return None
            headers = {"User-Agent": UA, "Referer": self.host + "/", "Accept": "image/*"}
            rr = rq.get(url, headers=headers, timeout=15, verify=False, allow_redirects=True)
            if rr.status_code == 200 and rr.content and len(rr.content) > 50:
                data = _decrypt_img(rr.content)
                ctype = _detect_mime(data)
                return [200, ctype, data]
        except Exception:
            pass
        return None

    def _proxy_pic(self, params):
        try:
            raw = params.get("url") or ""
            if not raw.startswith("http"):
                try:
                    raw = base64.b64decode(raw + "==").decode("utf-8", "ignore")
                except Exception:
                    pass
            if not raw.startswith("http"):
                return None
            headers = {"User-Agent": UA, "Referer": self.host + "/"}
            data = rq.get(raw, headers=headers, timeout=15, verify=False).content
            data = _decrypt_img(data)
            mime = _detect_mime(data)
            return [200, mime, data]
        except Exception:
            return None

    @staticmethod
    def _resolve_img_param(param):
        if not param:
            return ""
        p = str(param).strip()
        p = re.sub(r'^https?://127\.0\.0\.1:\d+/proxy\?', '', p)
        p = re.sub(r'^proxy\?', '', p)
        if "url=" in p:
            q = urllib.parse.parse_qs(p)
            cand = q.get("url", [""])[0]
            if cand:
                p = cand
        try:
            p = urllib.parse.unquote(p)
        except Exception:
            pass
        if not p.startswith("http"):
            try:
                dec = base64.b64decode(p + "==").decode("utf-8", "ignore")
                if dec.startswith("http"):
                    p = dec
            except Exception:
                pass
        return p if p.startswith("http") else ""

    # ---------- 列表解析 ----------
    def _parse_list(self, html, mode="drama"):
        if not html or len(html) < 150:
            return []
        if BeautifulSoup is not None:
            try:
                return self._parse_bs4(html, mode)
            except Exception:
                pass
        return self._parse_regex(html)

    def _parse_bs4(self, html, mode):
        videos, seen = [], set()
        doc = BeautifulSoup(html, _BS4_PARSER or "html.parser")

        if mode == "drama" or mode == "search":
            for card in doc.select("div.hg-drama-card"):
                a = card.find("a", href=True)
                if not a:
                    continue
                href = a.get("href", "")
                m = re.search(r"/(?:detail|video)/(\d+)", href)
                if not m:
                    continue
                vid = m.group(1)
                if vid in seen:
                    continue
                seen.add(vid)
                img = card.find("img")
                pic = ""
                if img:
                    pic = img.get("data-src") or img.get("src") or ""
                title = ""
                if img:
                    title = img.get("alt") or ""
                if not title:
                    t = card.select_one(".hg-drama-card__title a, .hg-drama-card__title, h2, h3")
                    title = t.get_text(strip=True) if t else ""
                if not title:
                    title = card.get("data-track-title") or ""
                parts = []
                for sel in [".hg-drama-card__score", ".hg-drama-card__episode",
                            ".hg-drama-card__badge"]:
                    el = card.select_one(sel)
                    if el:
                        parts.append(el.get_text(strip=True))
                remark = " ".join(parts).strip() or "在线观看"
                if title:
                    videos.append({
                        "vod_id": vid,
                        "vod_name": _clean(title),
                        "vod_pic": self._wrap_pic(pic),
                        "vod_remarks": remark,
                    })

            if mode == "search" and not videos:
                for a in doc.find_all("a", href=re.compile(r"/(?:detail|video)/\d+")):
                    m = re.search(r"/(?:detail|video)/(\d+)", a.get("href", ""))
                    if not m or m.group(1) in seen:
                        continue
                    seen.add(m.group(1))
                    img = a.find("img")
                    if not img:
                        continue
                    pic = img.get("data-src") or img.get("src") or ""
                    title = img.get("alt") or img.get("title") or a.get("title") or ""
                    if not title:
                        t = a.find(class_=re.compile("title"))
                        title = t.get_text(strip=True) if t else ""
                    remark = ""
                    for cls in ["episode", "score"]:
                        s = a.find(class_=re.compile(cls))
                        if s:
                            remark = s.get_text(strip=True)
                            break
                    if title:
                        videos.append({
                            "vod_id": m.group(1),
                            "vod_name": _clean(title),
                            "vod_pic": self._wrap_pic(pic),
                            "vod_remarks": remark or "在线观看",
                        })

        elif mode == "rank":
            for item in doc.select("div.hg-rank-item"):
                a = item.find("a", href=True, class_=re.compile("cover")) or item.find("a", href=True)
                if not a:
                    continue
                href = a.get("href", "")
                m = re.search(r"/(?:detail|video)/(\d+)", href)
                vid = m.group(1) if m else href
                if vid in seen:
                    continue
                seen.add(vid)
                img = item.find("img")
                pic = (img.get("data-src") or img.get("src") or "") if img else ""
                title = item.get("data-track-title") or (img.get("alt") if img else "") or ""
                if not title:
                    t = item.select_one(".hg-rank-item__title, h2")
                    title = t.get_text(strip=True) if t else ""
                heat = item.select_one(".hg-rank-item__heat-value")
                remark = ("🔥" + heat.get_text(strip=True)) if heat else ""
                if title:
                    videos.append({
                        "vod_id": vid,
                        "vod_name": _clean(title),
                        "vod_pic": self._wrap_pic(pic),
                        "vod_remarks": remark,
                    })

        elif mode == "topic":
            for card in doc.select("a.hg-topic-card"):
                href = card.get("href", "")
                slug = href.strip("/").split("/")[-1]
                img = card.find("img")
                pic = (img.get("data-src") or img.get("src") or "") if img else ""
                t = card.select_one(".hg-topic-card__title, h2")
                title = t.get_text(strip=True) if t else (img.get("alt") if img else "")
                meta = card.select_one(".hg-topic-card__meta")
                remark = meta.get_text(strip=True) if meta else ""
                if title:
                    videos.append({
                        "vod_id": "dir_topic_" + slug,
                        "vod_name": _clean(title),
                        "vod_pic": self._wrap_pic(pic),
                        "vod_remarks": remark,
                        "vod_tag": "folder",
                    })

        elif mode == "post":
            for card in doc.select("a.hg-post-card"):
                href = card.get("href", "")
                if not href:
                    continue
                img = card.find("img")
                pic = (img.get("data-src") or img.get("src") or "") if img else ""
                h3 = card.find("h3")
                title = h3.get_text(strip=True) if h3 else ""
                date = card.select_one(".hg-post-card__date")
                cat = card.select_one(".hg-post-card__cat")
                parts = [s.get_text(strip=True) for s in (date, cat) if s]
                videos.append({
                    "vod_id": href if href.startswith("http") else self.host + href,
                    "vod_name": _clean(title),
                    "vod_pic": self._wrap_pic(pic),
                    "vod_remarks": " | ".join(parts),
                })

        return videos

    def _parse_regex(self, html):
        result, seen = [], set()
        for block in re.split(r'<div class="hg-drama-card"', html)[1:]:
            m = re.search(r'href="(/(?:detail|video)/(\d+)/?)"', block)
            if not m:
                continue
            vid = m.group(2)
            if vid in seen:
                continue
            pic = ""
            pm = re.search(r'data-src="([^"]+)"', block)
            if pm:
                pic = htmllib.unescape(pm.group(1)).strip()
            if not pic:
                pm = re.search(r'<img[^>]*src="([^"]+)"', block)
                if pm:
                    pic = htmllib.unescape(pm.group(1)).strip()
            title = ""
            tm = re.search(
                r'class="[^"]*hg-drama-card__title[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>',
                block, re.S)
            if tm:
                title = _clean(tm.group(1))
            if not title:
                tm = re.search(r'<img[^>]*alt="([^"]+)"', block)
                if tm:
                    title = _clean(tm.group(1))
            parts = []
            sm = re.search(r'class="hg-drama-card__score">([^<]+)<', block)
            if sm:
                parts.append(_clean(sm.group(1)))
            em = re.search(r'class="hg-drama-card__episode">([^<]+)<', block)
            if em:
                parts.append(_clean(em.group(1)))
            remark = " ".join(parts).strip() or "在线观看"
            if not title:
                continue
            seen.add(vid)
            result.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._wrap_pic(pic),
                "vod_remarks": remark,
            })
        return result
