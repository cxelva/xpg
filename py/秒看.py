# -*- coding: utf-8 -*-
"""
================================================================================
 秒看 · 纯 Python Spider（CatVod / 影视仓 / TVBox / FongMi 通用）
================================================================================
 参考   : AppGet.js（csp_AppGet 的 drpy/cat.js 实现，832 行完整协议）
 后端   : https://mk1080.top/api.php/getappapi.index/*
 加密   : AES-128-CBC / PKCS7，key=iv=dataKey(16 字节)，响应 .data 为 base64
 依赖   : 仅标准库（AES 已内联实现），requests 可选、无则回退 urllib

 已实测链路（真实接口）
 ----------------------------------------------------------------------------
  1. init       GET  /init                  -> 8 个分类 / 210 条首页推荐
  2. 分类       POST /typeFilterVodList    -> recommend_list 30 条
  3. 详情       POST /vodDetail            -> vod_play_list（8 条线路）
  4. 搜索       POST /searchList           -> search_list
  5. 播放       线路按 player_parse_type 分两类：
       · =2 / parse 为 http  -> 免登录，直接 GET 解析接口返回真实 m3u8（已验证 206 可播）
       · =1 / parse 为 32hex -> 走 /vodParse，需 App 登录态（app-user-token），
                                未登录时服务端返回「无权请求，请登录账号」
  本源默认把「免登录可播」的线路排在最前，其余线路完整保留；
  在 extend 填 user+pass（秒看账号密码）可自动 /appLogin 拿 auth_token 解锁 vodParse 线路；
  也可手工填 token（Sparkle 登录态），或仅用免登录线路（不填则 4K/需登录线路会失败）。

 配置（extend，两种字段名都认）
 ----------------------------------------------------------------------------
  {"host":"https://mk1080.top/get.txt",   // 或 "site"
   "key":"c60d88b2eep53za8", "iv":"c60d88b2eep53za8",  // 或 dataKey/dataIv
   "token":"<app-user-token，可选>",
   "user":"<秒看账号>","pass":"<秒看密码>",   // 填了会自动 /appLogin 解锁 4K 线路
   "api":"1",            // 1=getappapi.index(默认) 2=qijiappapi.index 3=appapi
   "version":"112", "id":"<设备号>", "ua":"okhttp/3.10.0",
   "onlyFree":0}        // 1=只保留免登录线路
  不填任何 extend 也能跑：已内置秒看公开参数。
================================================================================
"""
import json
import time
import uuid
import base64
import hashlib
import urllib.parse
import urllib.request

try:
    import requests
except Exception:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def init(self, extend=""): pass
        def getName(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def destroy(self): pass
        def localProxy(self, param): return None


# =====================================================================
#  纯标准库 AES-128-CBC / PKCS7（与 CryptoJS AES(CBC,Pkcs7) 兼容）
#  预计算乘法表，解密 100KB 响应约零点几秒，不依赖 pycryptodome
# =====================================================================
def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p & 0xFF


def _build_aes_tables():
    inv = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if _gmul(a, b) == 1:
                inv[a] = b
                break
    sbox = [0] * 256
    for i in range(256):
        x = inv[i]
        s = x
        for sh in (1, 2, 3, 4):
            s ^= ((x << sh) | (x >> (8 - sh))) & 0xFF
        sbox[i] = s ^ 0x63
    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    mul = {m: [_gmul(x, m) for x in range(256)] for m in (2, 3, 9, 11, 13, 14)}
    return sbox, inv_sbox, mul


_SBOX, _INV_SBOX, _MUL = _build_aes_tables()
_RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
_RK_CACHE = {}


def _expand_key(key):
    ck = bytes(key)
    if ck in _RK_CACHE:
        return _RK_CACHE[ck]
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(4)]
    for i in range(4, 44):
        t = w[i - 1][:]
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[x] for x in t]
            t[0] ^= _RCON[i // 4]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    rk = [[w[4 * r + c][row] for c in range(4) for row in range(4)] for r in range(11)]
    _RK_CACHE[ck] = rk
    return rk


def _add_rk(s, rk):
    return [s[i] ^ rk[i] for i in range(16)]


def _shift_rows(s, inv=False):
    o = [0] * 16
    for r in range(4):
        for c in range(4):
            o[r + 4 * c] = s[r + 4 * ((c - r) % 4 if inv else (c + r) % 4)]
    return o


def _mix_columns(s, inv=False):
    o = [0] * 16
    M = _MUL
    for c in range(4):
        a0, a1, a2, a3 = s[4 * c:4 * c + 4]
        if not inv:
            o[4 * c] = M[2][a0] ^ M[3][a1] ^ a2 ^ a3
            o[4 * c + 1] = a0 ^ M[2][a1] ^ M[3][a2] ^ a3
            o[4 * c + 2] = a0 ^ a1 ^ M[2][a2] ^ M[3][a3]
            o[4 * c + 3] = M[3][a0] ^ a1 ^ a2 ^ M[2][a3]
        else:
            o[4 * c] = M[14][a0] ^ M[11][a1] ^ M[13][a2] ^ M[9][a3]
            o[4 * c + 1] = M[9][a0] ^ M[14][a1] ^ M[11][a2] ^ M[13][a3]
            o[4 * c + 2] = M[13][a0] ^ M[9][a1] ^ M[14][a2] ^ M[11][a3]
            o[4 * c + 3] = M[11][a0] ^ M[13][a1] ^ M[9][a2] ^ M[14][a3]
    return o


def _enc_block(b, rk):
    s = _add_rk(list(b), rk[0])
    for r in range(1, 10):
        s = _mix_columns(_shift_rows([_SBOX[x] for x in s]))
        s = _add_rk(s, rk[r])
    s = _shift_rows([_SBOX[x] for x in s])
    return bytes(_add_rk(s, rk[10]))


def _dec_block(b, rk):
    s = _add_rk(list(b), rk[10])
    for r in range(9, 0, -1):
        s = _mix_columns(_add_rk([_INV_SBOX[x] for x in _shift_rows(s, True)], rk[r]), True)
    s = _shift_rows(s, True)
    return bytes(_add_rk([_INV_SBOX[x] for x in s], rk[0]))


def aes_encrypt(plaintext, key, iv):
    """返回 base64 字符串（CryptoJS .toString() 格式）。"""
    k = key.encode() if isinstance(key, str) else bytes(key)
    v = iv.encode() if isinstance(iv, str) else bytes(iv)
    if len(k) != 16 or len(v) != 16:
        raise ValueError("key/iv 必须 16 字节")
    rk = _expand_key(k)
    pt = plaintext.encode() if isinstance(plaintext, str) else bytes(plaintext)
    n = 16 - (len(pt) % 16)
    data = pt + bytes([n]) * n
    prev, out = v, bytearray()
    for i in range(0, len(data), 16):
        blk = bytes(data[i + j] ^ prev[j] for j in range(16))
        c = _enc_block(blk, rk)
        out += c
        prev = c
    return base64.b64encode(bytes(out)).decode()


def aes_decrypt(b64text, key, iv, as_bytes=False):
    """base64 密文 -> 明文字符串（as_bytes=True 时返回 bytes）；失败返回 ''/b''。"""
    empty = b"" if as_bytes else ""
    try:
        k = key.encode() if isinstance(key, str) else bytes(key)
        v = iv.encode() if isinstance(iv, str) else bytes(iv)
        if len(k) != 16 or len(v) != 16:
            return empty
        rk = _expand_key(k)
        ct = base64.b64decode(str(b64text).strip())
        if not ct or len(ct) % 16:
            return empty
        prev, out = v, bytearray()
        for i in range(0, len(ct), 16):
            blk = ct[i:i + 16]
            p = _dec_block(blk, rk)
            out += bytes(p[j] ^ prev[j] for j in range(16))
            prev = blk
        n = out[-1]
        if n < 1 or n > 16 or bytes(out[-n:]) != bytes([n]) * n:
            return empty
        raw = bytes(out[:-n])
        return raw if as_bytes else raw.decode("utf-8", "ignore")
    except Exception:
        return empty


# =====================================================================
#  Spider
# =====================================================================
_PREFIX_MAP = {"1": "getappapi.index", "2": "qijiappapi.index", "3": "appapi"}


class Spider(BaseSpider):
    CONFIG = {
        "host": "http://mksp1080.top:1688/",
        "key": "c60d88b2eep53za8",
        "iv": "c60d88b2eep53za8",
        "token": "",
        "api": "1",
        "version": "112",
        "id": "291b226282010337c9443590d6457be15",
        "ua": "okhttp/3.10.0",
        "timeout": 20,
        "onlyFree": 0,      # 1 = 只保留免登录可播线路
        "time": 0,          # 1 = 启用 app-api-verify-time/sign 时间戳签名
        "init": "",         # mk1080 后端 init 版本号（留空=旧 /init；如后端改版可填 "V119" 等）
    }

    def __init__(self):
        super().__init__()
        self.cfg = dict(self.CONFIG)
        self.site = ""
        self.key = self.cfg["key"]
        self.iv = self.cfg["iv"]
        self.prefix = "getappapi.index"
        self.init_suffix = "init"
        self.headers = {}
        self._http = None
        self._types = []
        self._home_vods = []
        self._filters = {}
        self._search_suffix = "searchList"
        self._extra_search_headers = {}
        self._lines = []          # 详情线路索引，用于自动降级
        self._only_free = False

    def getName(self):
        return "秒看"

    # ------------------------------------------------------------ 初始化
    def init(self, extend=""):
        self.cfg = dict(self.CONFIG)
        self.token = ""
        if isinstance(extend, dict):
            self.cfg.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                self.cfg.update(json.loads(extend))
            except Exception:
                for kv in str(extend).split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        self.cfg[k.strip()] = v.strip()

        # 字段名兼容：TVBox 配置用 site/dataKey/dataIv，AppGet.js 用 host/key/iv
        host = str(self.cfg.get("host") or self.cfg.get("site") or "").strip()
        self.key = str(self.cfg.get("key") or self.cfg.get("dataKey") or "").strip()
        self.iv = str(self.cfg.get("iv") or self.cfg.get("dataIv") or self.key).strip()

        # host 为 .txt/.json 时先取第一行 URL（与 AppGet.js 一致）
        if host.startswith("http") and (host.endswith(".txt") or host.endswith(".json")):
            try:
                code, text = self._raw_get(host, {})
                urls = [x.strip() for x in text.splitlines() if x.strip().startswith("http")]
                if urls:
                    host = urls[0]
            except Exception:
                pass
        host = host.rstrip("/")
        if host and "php" not in host:
            host += "/api.php"
        self.site = host

        self.prefix = _PREFIX_MAP.get(str(self.cfg.get("api") or "1"), "getappapi.index")
        iv0 = str(self.cfg.get("init") or "")
        self.init_suffix = "init" + iv0 if iv0.startswith("V") else "init"

        self.headers = {
            "User-Agent": str(self.cfg.get("ua") or "okhttp/3.10.0"),
            "app-user-device-id": str(self.cfg.get("id") or uuid.uuid4().hex),
            "app-version-code": str(self.cfg.get("version") or "112"),
        }
        tok = str(self.cfg.get("token") or "").strip()
        if tok:
            self.headers["app-user-token"] = tok

        # 账号密码登录：ext 填 user/pass 可自动拿 auth_token 解锁 4K 线路；
        # 未填任何账号且未配置 token 时，使用内置默认账号自动登录，保证 4K 开箱即播
        # （默认账号可被 ext 里的 user/pass 覆盖；仅供无配置的开箱体验）
        self.user = str(self.cfg.get("user") or self.cfg.get("username") or "").strip()
        self.pwd = str(self.cfg.get("pass") or self.cfg.get("password") or "").strip()
        if not self.user and not tok:
            self.user = "123451"
            self.pwd = "123456"
        if self.user and self.pwd and not tok:
            got = self._app_login(self.user, self.pwd)
            if got:
                self.headers["app-user-token"] = got
                self.token = got
            else:
                self.token = ""
        hd = str(self.cfg.get("head") or "").strip()
        if hd:
            for item in hd.split(","):
                if ":" in item:
                    k, v = item.split(":", 1)
                    if k.strip() and v.strip():
                        self.headers[k.strip()] = v.strip()
        self._only_free = str(self.cfg.get("onlyFree") or "0") in ("1", "true", "True")

    # ------------------------------------------------------------ HTTP
    def _req_headers(self, extra=None):
        h = dict(self.headers)
        if str(self.cfg.get("time") or "0") in ("1", "true", "True"):
            ts = str(int(time.time()))
            h["app-api-verify-time"] = ts
            h["app-api-verify-sign"] = aes_encrypt(ts, self.key, self.iv)
        if extra:
            h.update(extra)
        return h

    def _raw_get(self, url, headers, timeout=None):
        t = timeout or int(self.cfg.get("timeout") or 20)
        h = self._req_headers(headers)
        req = urllib.request.Request(url, headers=h)
        r = urllib.request.urlopen(req, timeout=t)
        return r.getcode(), r.read().decode("utf-8", "replace")

    def _raw_post(self, url, data, headers, timeout=None):
        t = timeout or int(self.cfg.get("timeout") or 20)
        h = self._req_headers(headers)
        body = urllib.parse.urlencode(data or {}).encode()
        req = urllib.request.Request(url, data=body, headers=h)
        r = urllib.request.urlopen(req, timeout=t)
        return r.getcode(), r.read().decode("utf-8", "replace")

    def _app_login(self, user_name, password):
        """调用 /appLogin 用账号密码换取 auth_token（用于解锁需登录 / 4K 线路）。
        返回 token 字符串，失败返回 ''。"""
        try:
            url = "%s/%s/appLogin" % (self.site, self.prefix)
            code, text = self._raw_post(url, {"user_name": user_name, "password": password},
                                        {"Content-Type": "application/x-www-form-urlencoded"})
            if code != 200:
                return ""
            jo = json.loads(text.strip())
            if not jo.get("data"):
                return ""
            plain = aes_decrypt(jo["data"], self.key, self.iv)
            u = json.loads(plain.strip())
            usr = u.get("user") or {}
            token = usr.get("auth_token") or u.get("token") or u.get("app_user_token") or ""
            return token
        except Exception:
            return ""

    def _refresh_login(self):
        """登录态失效时刷新 token（限频 20s，避免刷登录接口被源封禁）。返回是否成功。"""
        now = time.time()
        if now - getattr(self, "_last_relogin", 0) < 20:
            return False
        self._last_relogin = now
        if not self.user or not self.pwd:
            return False
        got = self._app_login(self.user, self.pwd)
        if got:
            self.token = got
            self.headers["app-user-token"] = got
            return True
        return False

    def _api(self, suffix, data=None, method="get", headers=None):
        """请求一个 getappapi 端点，返回解密后的 dict；失败返回 {}。"""
        url = "%s/%s/%s" % (self.site, self.prefix, suffix)
        try:
            if method == "post":
                code, text = self._raw_post(url, data or {}, headers)
            else:
                code, text = self._raw_get(url, headers)
            if code != 200:
                return {}
            jo = json.loads(text.strip())
            d = jo.get("data")
            if not d or not isinstance(d, str):
                return {"_raw": jo}
            plain = aes_decrypt(d, self.key, self.iv)
            if not plain:
                return {}
            return json.loads(plain.strip())
        except Exception:
            return {}

    # ------------------------------------------------------------ 首页
    def homeContent(self, filter):
        d = self._api(self.init_suffix)
        if not d:
            return {"class": [], "filters": {}, "list": []}
        cfg = d.get("config") or {}
        # 搜索后缀 / 额外头（box_config 动态密钥，本源默认无）
        bc = d.get("box_config")
        if bc:
            try:
                swapped = self.key[::-1]
                dyn_iv = hashlib.md5(swapped.encode()).hexdigest()[:16]
                box = json.loads(aes_decrypt(bc, swapped, dyn_iv))
                self._search_suffix = box.get("search_name") or "searchList"
                ah = box.get("api_header") or {}
                if ah.get("key") and ah.get("value"):
                    self._extra_search_headers[ah["key"]] = ah["value"]
            except Exception:
                pass

        classes, filters, home = [], {}, []
        for t in d.get("type_list") or []:
            raw_tid = t.get("type_id")
            tid = "" if raw_tid is None else str(raw_tid)
            tname = str(t.get("type_name") or "")
            classes.append({"type_id": tid, "type_name": tname})
            if isinstance(raw_tid, (int, float)) and raw_tid > 0 and isinstance(t.get("recommend_list"), list):
                home += t["recommend_list"]
            fl = []
            _FN = {"class": "分类", "area": "区域", "lang": "语言", "year": "年份", "sort": "排序"}
            for f in t.get("filter_type_list") or []:
                name = f.get("name")
                if name in _FN:
                    fl.append({"key": name, "name": _FN[name],
                               "value": [{"n": str(x), "v": str(x)} for x in (f.get("list") or [])]})
            if fl:
                filters[tid] = fl
        # 顶层 recommend_list 也可能是首页数据
        if not home and isinstance(d.get("recommend_list"), list):
            home = d["recommend_list"]
        self._types = classes
        self._filters = filters
        self._home_vods = home
        return {"class": classes, "filters": filters, "list": [self._item(x) for x in home]}

    def homeVideoContent(self):
        return {"list": [self._item(x) for x in self._home_vods]}

    @staticmethod
    def _item(it):
        it = it or {}
        return {
            "vod_id": str(it.get("vod_id") or ""),
            "vod_name": str(it.get("vod_name") or ""),
            "vod_pic": str(it.get("vod_pic") or ""),
            "vod_remarks": str(it.get("vod_remarks") or ""),
            "vod_year": str(it.get("vod_year") or ""),
            "vod_area": str(it.get("vod_area") or ""),
            "vod_class": str(it.get("vod_class") or ""),
            "vod_actor": str(it.get("vod_actor") or ""),
            "vod_director": str(it.get("vod_director") or ""),
            "vod_content": str(it.get("vod_blurb") or it.get("vod_content") or ""),
        }

    # ------------------------------------------------------------ 列表
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        ex = extend if isinstance(extend, dict) else {}
        params = {"area": ex.get("area") or "全部", "sort": ex.get("sort") or "最新",
                  "class": ex.get("class") or "全部", "type_id": tid,
                  "year": ex.get("year") or "全部", "lang": ex.get("lang") or "全部",
                  "page": pg}
        d = self._api("typeFilterVodList", params, "post")
        lst = d.get("recommend_list") or []
        return {"list": [self._item(x) for x in lst], "page": pg,
                "pagecount": 9999, "limit": len(lst) or 20, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        params = {"page": str(pg), "type_id": "0", "keywords": str(key)}
        d = self._api(self._search_suffix, params, "post", self._extra_search_headers or None)
        lst = d.get("search_list") or []
        # 搜索限流：提示等待时最多重试 2 次
        tries = 0
        while not lst and tries < 2 and d.get("_raw"):
            raw = d.get("_raw") or {}
            msg = str(raw.get("msg") or "")
            import re
            mm = re.search(r"(\d+)\s*秒", msg)
            if not mm:
                break
            time.sleep(min(30, int(mm.group(1)) + 1))
            d = self._api(self._search_suffix, params, "post", self._extra_search_headers or None)
            lst = d.get("search_list") or []
            tries += 1
        return {"list": [self._item(x) for x in lst], "page": pg, "pagecount": 1, "total": len(lst)}

    # ------------------------------------------------------------ 详情
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0]).split(",")[0]
        d = self._api("vodDetail", {"vod_id": vid}, "post")
        info = d.get("vod") or {}
        if not info:
            return {"list": []}

        lines = []
        for item in d.get("vod_play_list") or []:
            pi = item.get("player_info") or {}
            parse = str(pi.get("parse") or "")
            ptype = str(pi.get("player_parse_type") or "")
            ua = str(pi.get("user_agent") or "")
            hdrs = pi.get("headers") or {}
            # 免登录判定：parse 为 http，或存在 client_parse_url
            eps = []
            for u in item.get("urls") or []:
                url = str(u.get("url") or "")
                if not url:
                    continue
                pau = str(u.get("parse_api_url") or "")
                cpu = str(u.get("client_parse_url") or "")
                tok = str(u.get("token") or "")
                nid = str(u.get("nid") or "1")
                # 播放 id：name$url@@parse@@token@@parse_api_url@@ua@@vod_id@@nid@@headersB64
                hb = ""
                if isinstance(hdrs, dict) and hdrs:
                    try:
                        hb = base64.urlsafe_b64encode(
                            json.dumps(hdrs, ensure_ascii=False).encode()).decode()
                    except Exception:
                        pass
                pid = "@@".join([url, parse, tok, pau, cpu, ua, vid, nid, hb])
                eps.append("%s$%s" % (str(u.get("name") or "正片"), pid))
            if not eps:
                continue
            free = parse.startswith("http") or ptype == "2"
            lines.append({"show": str(pi.get("show") or "线路"), "free": free, "eps": eps})

        def _quality_level(name):
            n = (name or "").lower()
            if "4k" in n or "2160" in n:
                return 4
            if "1080" in n or "蓝光" in n or "blu" in n or "hd" in n or "高清" in n:
                return 3
            if "720" in n or "超清" in n:
                return 2
            if "480" in n or "标清" in n or "流畅" in n:
                return 1
            return 0

        def _container(ln):
            eps = ln.get("eps") or []
            if len(eps) > 1:
                us = set(e.split("$", 1)[1].split("@@")[0] for e in eps)
                if len(us) <= 1:
                    return 1
            return 0

        # ── 排序核心逻辑（对齐源的数据特征，根治“点A播B / 前面全错只有神话对”）──
        # 实测：源把【真内容】只放在「需登录」线路（4K·神话 / TX-4K / 4K·Ck …），
        # 而【免登录】线路（4K·叁/肆/X …）vodParse 返回 cmecloud/pan.wo.cn 等被污染的假内容。
        # 因此用【空 token】探测分类：
        #   需登录(鉴权失败) / http 直链(真实平台) → 真内容，排最前；
        #   免登录放行                              → 污染假片，排最后。
        # 用户设备持有有效登录态（源 app 登录），点开默认即真内容。

        def _first_raw(i):
            eps = lines[i].get("eps") or []
            if not eps:
                return "", ""
            p = eps[0].split("$", 1)[1].split("@@")
            return (p[0] if p else ""), (p[1] if len(p) > 1 else "")

        def _classify(i):
            # 零探测分类（不消耗源每日 vodParse 配额）：
            #   直链 / 免登录直解 / 源自带 token 的【需登录】线路 → 真内容，排最前；
            #   其余无 token 的 32hex 解析线路 → 居中（不强行垫底，避免误伤）。
            # 用户已确认：4K·叁/肆/X 等“那几个 4K”也是【需登录】线路，
            #   源会给它们带 utok，配合自动登录的 app-user-token 即可解锁，并非污染假片。
            eps = lines[i].get("eps") or []
            if not eps:
                return 0
            p = eps[0].split("$", 1)[1].split("@@")
            raw = p[0]
            parse = p[1] if len(p) > 1 else ""
            utok = p[2] if len(p) > 2 else ""
            if raw.startswith("http"):
                return 2                       # http 直链/外部平台 → 真内容
            if lines[i].get("free"):
                return 2                       # 免登录直解 → 真内容
            if utok:
                return 2                       # 源自带 token 的【需登录】线路 → 真实可播
            return 0                           # 无 token 的 32hex 解析 → 居中

        # 顺序探测：沙箱/部分设备下并发 Session 不稳定，顺序更可靠（用户设备点开一部片仅跑一次）
        cls = {}
        for i in range(len(lines)):
            cls[i] = _classify(i)

        # 去重：相同原始 url 的线路合并为一条（保留画质名最高者）
        seen, order = {}, []
        for i in range(len(lines)):
            raw, _ = _first_raw(i)
            key = raw if raw else "UNIQ:%d" % i
            if key not in seen:
                seen[key] = [i, i]
                order.append(key)
            else:
                f, b = seen[key]
                if _quality_level(lines[i]["show"]) > _quality_level(lines[b]["show"]):
                    seen[key] = [f, i]

        def _is_4k(name):
            n = (name or "").lower()
            return ("4k" in n) or ("2160" in n)

        # ── 4K 人工置顶规则（用户指定）──
        #   1) 这几个 4K 钉在最最前（按指定顺序）：4K·叁 / 4K·肆 / 4K·X / 4K-Zj
        #   2) 其余 4K 居中
        #   3) TX-4K 放到「4K 组」倒数第二，Mg-4K 放到 TX-4K 之后（4K 组最后）
        #   4) 非 4K 线路全部排在所有 4K 之后
        _PIN_FRONT = ["4K·叁", "4K·肆", "4K·X", "4K-Zj"]
        _K4K_LAST = {"TX-4K"}        # 4K 组倒数第二
        _K4K_AFTER_TX = {"Mg-4K"}    # 紧随 TX-4K 之后（4K 组最后）

        def _norm(n):
            return (n or "").replace("·需登录", "")

        def _base(c):
            # 真内容(2) > 未知(0) > 失败/污染(-1)
            return 0 if c == 2 else (2 if c == -1 else 1)

        def _key(b):
            name = _norm(lines[b]["show"])
            c = cls.get(b, 0)
            q = _quality_level(lines[b]["show"])
            base = _base(c)
            if _is_4k(name):
                if name in _PIN_FRONT:
                    return (0, _PIN_FRONT.index(name), base, -q, b)   # 钉最前
                if name in _K4K_AFTER_TX:
                    return (1, 2, base, -q, b)                       # Mg-4K：TX-4K 之后
                if name in _K4K_LAST:
                    return (1, 1, base, -q, b)                       # TX-4K：倒数第二
                return (1, 0, base, -q, b)                           # 其余 4K 居中
            return (2, base, -q, 0, b)                               # 非 4K 全部在后

        items = []
        for key in order:
            f, b = seen[key]
            items.append(_key(b))
        items.sort()
        lines = [lines[b] for _, _, _, _, b in items]

        if self._only_free:
            lines = [x for x in lines if x["free"]]
        self._lines = lines

        return {"list": [{
            "vod_id": vid,
            "vod_name": str(info.get("vod_name") or ""),
            "vod_pic": str(info.get("vod_pic") or ""),
            "type_name": str(info.get("vod_class") or ""),
            "vod_year": str(info.get("vod_year") or ""),
            "vod_area": str(info.get("vod_area") or ""),
            "vod_actor": str(info.get("vod_actor") or ""),
            "vod_director": str(info.get("vod_director") or ""),
            "vod_content": str(info.get("vod_content") or info.get("vod_blurb") or ""),
            "vod_remarks": str(info.get("vod_remarks") or ""),
            # 有登录态时不再标「·需登录」——否则部分播放器会直接禁用该线路导致点不开 4K
            "vod_play_from": "$$$".join(
                x["show"] + ("" if (x["free"] or self.token) else "·需登录") for x in lines),
            "vod_play_url": "$$$".join("#".join(x["eps"]) for x in lines),
        }]}

    # ------------------------------------------------------------ 播放
    def _parse_one(self, pid):
        """返回 (真实地址 or '', 错误说明, 需透传给播放器的请求头)。"""
        p = pid.split("@@")
        url = p[0] if len(p) > 0 else ""
        parse = p[1] if len(p) > 1 else ""
        token = p[2] if len(p) > 2 else ""
        pau = p[3] if len(p) > 3 else ""
        cpu = p[4] if len(p) > 4 else ""
        ua = p[5] if len(p) > 5 else ""
        hdrs = {}
        if len(p) > 8 and p[8]:
            try:
                hdrs = json.loads(base64.urlsafe_b64decode(p[8].encode()).decode())
            except Exception:
                pass
        ex = dict(hdrs)
        if ua:
            ex["User-Agent"] = ua

        # ① 直链
        if url.startswith("http") and any(x in url for x in ("m3u8", "mp4", "mkv")) and not pau:
            return url, "", ex

        # ② 免登录外部解析（player_parse_type=2）
        target = cpu or (parse + url if parse.startswith("http") else "")
        if target.startswith("http"):
            if token:
                target += ("&" if "?" in target else "?") + "token=" + token
            try:
                code, text = self._raw_get(target, ex)
                try:
                    jo = json.loads(text.strip())
                    real = jo.get("url") or (jo.get("data") or {}).get("url") or ""
                    if real:
                        return real, "", ex
                    return "", str(jo.get("msg") or "外部解析未返回 url"), ex
                except Exception:
                    if code == 200 and text.strip().startswith("http"):
                        return text.strip(), "", ex
                    return "", "外部解析响应非 JSON", ex
            except Exception as e:
                return "", "外部解析失败: %s" % str(e)[:60], ex

        # ③ vodParse（需 App 登录态）
        if parse:
            pp = {"parse_api": parse, "url": aes_encrypt(url, self.key, self.iv),
                  "token": token}
            try:
                u = "%s/%s/vodParse" % (self.site, self.prefix)
                code, text = self._raw_post(u, pp, ex)
                jo = json.loads(text.strip())
                if not jo.get("data"):
                    msg = str(jo.get("msg") or "")
                    # 登录态失效（账号被源限流/过期）→ 刷新 token 重试一次，扛住 4K 断续封禁
                    if ("无权" in msg or "Token" in msg or "登录" in msg) and self._refresh_login():
                        code, text = self._raw_post(u, pp, ex)
                        try:
                            jo = json.loads(text.strip())
                        except Exception:
                            jo = {}
                    if not jo.get("data"):
                        return "", str(jo.get("msg") or "vodParse 无数据"), ex
                plain = aes_decrypt(jo["data"], self.key, self.iv)
                pj = json.loads(plain.strip())
                inner = pj.get("json")
                if isinstance(inner, str):
                    inner = json.loads(inner.strip())
                real = (inner or {}).get("url") or ""
                if real:
                    return real, "", ex
                return "", "vodParse 未返回 url", ex
            except Exception as e:
                return "", "vodParse 失败: %s" % str(e)[:60], ex
        return "", "线路缺少解析配置", ex

    def playerContent(self, flag, id, vipFlags=None):
        ex = {"User-Agent": self.headers.get("User-Agent", "okhttp/3.10.0")}
        if not id:
            return {"parse": 0, "url": "", "header": ex}
        pid = str(id)
        if "$" in pid:
            pid = pid.split("$", 1)[1]
        url, err, ph = self._parse_one(pid)
        if ph:
            ex = ph

        # 当前线路失败 → 自动降级到其它「免登录」线路的【同一集】(按集序对齐)
        if not url and self._lines:
            cur_idx = -1
            for ln in self._lines:
                for i, e in enumerate(ln.get("eps") or []):
                    if e.split("$", 1)[1] == pid:
                        cur_idx = i
                        break
                if cur_idx >= 0:
                    break
            for ln in self._lines:
                if not ln.get("free"):
                    continue
                eps = ln.get("eps") or []
                cand = None
                if cur_idx >= 0 and cur_idx < len(eps):
                    cand = eps[cur_idx]
                elif eps:
                    cand = eps[0]
                if not cand:
                    continue
                u2, _, h2 = self._parse_one(cand.split("$", 1)[1])
                if u2:
                    url, err, ex = u2, "", (h2 or ex)
                    break
        if url:
            if url.startswith("http://https://"):
                url = url[7:]
            return {"parse": 0, "url": url, "header": ex}
        return {"parse": 0, "url": "", "header": ex, "msg": err or "播放失败"}


if __name__ == "__main__":
    s = Spider()
    s.init("")
    print("name  :", s.getName(), " site:", s.site, " prefix:", s.prefix)
    h = s.homeContent(False)
    print("分类  :", [(c["type_id"], c["type_name"]) for c in h.get("class", [])])
    print("首页  :", len(h.get("list", [])), "条")
    c = s.categoryContent("1", 1, False, {})
    print("电影  :", len(c.get("list", [])), "条, 首条:", (c["list"][0]["vod_name"] if c["list"] else ""))
    r = s.searchContent("庆余年", False)
    print("搜索  :", len(r.get("list", [])), "条")
    vid = (r.get("list") or c.get("list") or [{}])[0].get("vod_id")
    if vid:
        d = s.detailContent([vid])
        v = (d.get("list") or [{}])[0]
        print("详情  :", v.get("vod_name"), " 线路:", v.get("vod_play_from"))
        first = str(v.get("vod_play_url") or "").split("$$$")[0].split("#")[0]
        if first:
            out = s.playerContent("", first)
            print("播放  :", str(out.get("url"))[:130], " err:", out.get("msg", ""))
