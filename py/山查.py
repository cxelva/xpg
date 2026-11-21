# -*- coding: utf-8 -*-
"""
米诺┃秒播  NewBox / TVBox PY 源
逆向自 csp_MiNO (catvod spider)。接口全部匿名可用：
  - 分类 / 搜索 / 详情 / 播放票据
  - ECDH 握手 + HMAC 请求签名 + AES-GCM 响应解密
  - 播放：detail -> vod/ticket -> vod/parse -> 真实 m3u8/mp4 直链
实测（2026-11-20）：7 条线路中「蓝光4K【推荐】」(duanju) 与「4K」(zijianm3u8)
均能匿名拿到真实地址；parse 返回 msg 里的"联系tg购买"只是残留模板文案，
code=200 时 url 字段即为真实播放链接，无需会员/购买。
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import sys
import time
import random

try:
    import requests
except ImportError:
    requests = None
import urllib.request
import urllib.error
from urllib.parse import quote, urlsplit

MINO_BUILD = "FIX4-DIAG"
_LAST_ERR = ""
_DIAG = {}


def _urandom(n):
    try:
        return os.urandom(n)
    except Exception:
        return bytes(random.randint(0, 255) for _ in range(n))

# ---------- HTTP ----------
UA = "okhttp/4.12.0"
DEFAULT_BASE = "http://43.248.128.122:578"
VER = "1.0.23"
SIGN_KEY_LABEL = b"bwv/apisec/ecdh-signkey/v1\x01"
BODY_KEY_LABEL = b"bwv/apisec/ecdh-bodykey/v1\x01"


def _http(method, url, body=None, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    data = body.encode("utf-8") if isinstance(body, str) else body
    if requests is not None:
        try:
            r = requests.request(method, url, data=data, headers=h, timeout=20)
            return r.content.decode("utf-8", "replace")
        except Exception:
            pass
    # 标准库回退（零依赖）
    try:
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.read().decode("utf-8", "replace")
        except Exception:
            return ""
    except Exception as e:
        global _LAST_ERR
        _LAST_ERR = "http:%s" % e
        return ""


def _b64e(b):
    return base64.b64encode(b).decode()


def _b64d(s):
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _hex(b):
    return binascii.hexlify(b).decode()


# ---------- P-256 ECDH (纯 Python，无外部依赖) ----------
_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
_A = _P - 3
_B = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
_GX = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296
_GY = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5
_N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551


def _inv(x, m):
    return pow(x, m - 2, m)


def _pt_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + _A) * _inv(2 * y1, _P) % _P
    else:
        lam = (y2 - y1) * _inv(x2 - x1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return (x3, y3)


def _pt_mul(k, pt):
    r = None
    while k > 0:
        if k & 1:
            r = _pt_add(r, pt)
        pt = _pt_add(pt, pt)
        k >>= 1
    return r


def _ecdh(priv_int, pub_bytes):
    """pub_bytes: 65 字节未压缩点 0x04||X||Y, 返回共享点 X 坐标(32字节)。"""
    if len(pub_bytes) == 65 and pub_bytes[0] == 4:
        qx = int.from_bytes(pub_bytes[1:33], "big")
        qy = int.from_bytes(pub_bytes[33:65], "big")
    elif len(pub_bytes) == 33 and pub_bytes[0] in (2, 3):
        qx = int.from_bytes(pub_bytes[1:], "big")
        ysq = (qx * qx * qx + _A * qx + _B) % _P
        qy = pow(ysq, (_P + 1) // 4, _P)
        if (qy % 2) != (pub_bytes[0] & 1):
            qy = _P - qy
    else:
        return b""
    shared = _pt_mul(priv_int, (qx, qy))
    if shared is None:
        return b""
    return shared[0].to_bytes(32, "big")


# ---------- AES-256-GCM (纯 Python 实现，零依赖) ----------
_SBOX = (
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
)

def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p


def _aes_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[i * 4:i * 4 + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= rcon
            rcon = _gmul(rcon, 2)
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _aes_block(w, nr, blk):
    s = [[blk[c * 4 + r] for r in range(4)] for c in range(4)]

    def ark(rd):
        for c in range(4):
            for r in range(4):
                s[c][r] ^= w[4 * rd + c][r]

    ark(0)
    for rd in range(1, nr):
        for c in range(4):
            for r in range(4):
                s[c][r] = _SBOX[s[c][r]]
        for r in range(1, 4):
            row = [s[c][r] for c in range(4)]
            for c in range(4):
                s[c][r] = row[(c + r) % 4]
        for c in range(4):
            a0, a1, a2, a3 = s[c]
            s[c][0] = _gmul(a0, 2) ^ _gmul(a1, 3) ^ a2 ^ a3
            s[c][1] = a0 ^ _gmul(a1, 2) ^ _gmul(a2, 3) ^ a3
            s[c][2] = a0 ^ a1 ^ _gmul(a2, 2) ^ _gmul(a3, 3)
            s[c][3] = _gmul(a0, 3) ^ a1 ^ a2 ^ _gmul(a3, 2)
        ark(rd)
    for c in range(4):
        for r in range(4):
            s[c][r] = _SBOX[s[c][r]]
    for r in range(1, 4):
        row = [s[c][r] for c in range(4)]
        for c in range(4):
            s[c][r] = row[(c + r) % 4]
    ark(nr)
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = s[c][r]
    return bytes(out)


def _aes_gcm_decrypt(key, nonce, ct):
    # GCM 解密即 CTR 模式：J0=nonce||00000001，从 counter=2 开始异或
    cipher = ct[:-16]  # 末 16 字节是 GCM tag
    j0 = int.from_bytes(nonce + b"\x00\x00\x00\x01", "big")
    w, nr = _aes_expand(key)
    out = bytearray()
    ctr = j0
    for i in range(0, len(cipher), 16):
        ctr = (ctr & ~0xffffffff) | ((ctr + 1) & 0xffffffff)
        ks = _aes_block(w, nr, ctr.to_bytes(16, "big"))
        chunk = cipher[i:i + 16]
        out.extend(a ^ b for a, b in zip(chunk, ks))
    return bytes(out)


try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


class Spider(_BaseSpider):
    def getName(self):
        return "米诺┃秒播"

    def init(self, ext=None):
        self.base = DEFAULT_BASE
        self.device = _hex(_urandom(8))  # 16 hex
        self._session = ""
        self._sign_key = None
        self._body_key = None
        self._expire = 0
        self._types = None
        self._filters = {}
        self._page_size = 20
        # 兼容 ext 里带 base（明文 json）
        try:
            if ext and ext.strip().startswith("{"):
                cfg = json.loads(ext)
                b = cfg.get("base", "")
                if b:
                    self.base = b.rstrip("/")
                if cfg.get("device_id"):
                    self.device = cfg["device_id"]
                self._page_size = max(5, min(100, int(cfg.get("page_size", 20))))
        except Exception:
            pass

    # ---- 握手 ----
    def _handshake(self):
        if self._sign_key and time.time() < self._expire:
            return True
        try:
            d = random.randint(1, _N - 1)
            pub = _pt_mul(d, (_GX, _GY))
            pub_bytes = b"\x04" + pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")
            payload = {
                "platform": "android", "version": VER, "device_id": self.device,
                "client_pub": _b64e(pub_bytes),
                "device_brand": "NewBox", "device_manufacturer": "NewBox", "device_model": "TVBox",
            }
            raw = _http("POST", self.base + "/api/v1/security/init",
                        json.dumps(payload, separators=(",", ":")),
                        {"Content-Type": "application/json"})
            if not raw:
                _DIAG["init"] = _LAST_ERR or ("no-response base=%s" % self.base)
                return False
            j = json.loads(raw)
            if j.get("code") != 1 or not isinstance(j.get("data"), dict):
                _DIAG["init"] = "code=%s msg=%s" % (j.get("code"), j.get("msg"))
                return False
            data = j["data"]
            session = data.get("session_id")
            server_pub = data.get("server_pub")
            if not session or not server_pub:
                # 回退旧版 sign_key
                sk = (data.get("sign_key") or "").encode("utf-8")
                if not sk:
                    return False
                self._session = session or ""
                self._sign_key = sk
                self._body_key = sk
                self._expire = time.time() + max(60, int(data.get("expires_in", 600)) - 30)
                self._server_time = int(data.get("server_time") or time.time())
                self._t0 = time.time()
                return True
            shared = _ecdh(d, _b64d(server_pub))
            if not shared:
                return False
            l2 = hmac.new(session.encode("utf-8"), shared, hashlib.sha256).digest()
            self._sign_key = hmac.new(l2, SIGN_KEY_LABEL, hashlib.sha256).digest()
            self._body_key = hmac.new(l2, BODY_KEY_LABEL, hashlib.sha256).digest()
            self._session = session
            self._server_time = int(data.get("server_time") or time.time())
            self._t0 = time.time()
            self._expire = time.time() + max(60, int(data.get("expires_in", 600)) - 30)
            return True
        except Exception:
            return False

    def _sort_query(self, params):
        """对应 Java i(encodedQuery)：先编码再按 key,value 排序。"""
        pairs = []
        for k, v in params.items():
            if v is None:
                continue
            pairs.append((quote(str(k), safe=""), quote(str(v), safe="")))
        pairs.sort(key=lambda x: (x[0], x[1]))
        return "&".join(k + "=" + v for k, v in pairs)

    def _call(self, method, path, params=None, body=None, raw_query=None):
        if not self._handshake():
            return {}
        params = params or {}
        query = raw_query if raw_query is not None else self._sort_query(params)
        url = self.base + path + ("?" + query if query else "")
        b = body or ""
        nonce = _hex(_urandom(16))
        body_sha = hashlib.sha256(b.encode("utf-8")).hexdigest()
        ts = str(self._server_time + int(time.time() - self._t0))
        msg = "%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s" % (
            method, path, query, body_sha, ts, nonce, self.device, self._session, VER)
        sig = hmac.new(self._sign_key, msg.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Session-Id": self._session,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Sign": sig,
            "X-Body-Sha256": body_sha,
            "X-App-Version": VER,
            "X-Device-Id": self.device,
        }
        try:
            j = json.loads(_http(method, url, b, headers))
        except Exception:
            return {}
        data = j.get("data")
        if isinstance(data, dict) and data.get("enc") == 1:
            try:
                p = _b64d(data.get("payload", ""))
                pt = _aes_gcm_decrypt(self._body_key, p[:12], p[12:])
                if pt:
                    j["data"] = json.loads(pt.decode("utf-8"))
            except Exception:
                return {}
        return j

    # ---- 分类 ----
    def _get_types(self):
        if self._types:
            return self._types
        j = self._call("GET", "/api/v1/search/types")
        self._types = (j.get("data") or []) if j.get("code") == 1 else []
        return self._types

    def homeContent(self, filter):
        result = {"class": [], "filters": {}, "list": []}
        try:
            types = self._get_types()
            for t in types:
                result["class"].append({"type_id": str(t.get("type_id")), "type_name": t.get("type_name", "")})
            if filter:
                for t in types:
                    tid = str(t.get("type_id"))
                    fj = self._call("GET", "/api/v1/category/filters", {"type_id": tid})
                    d = fj.get("data") or {}
                    fl = []
                    mapping = [("sorts", "sort", "排序"), ("areas", "area", "地区"),
                               ("years", "year", "年份"), ("langs", "lang", "语言"),
                               ("classes", "class", "类型")]
                    for key, k, name in mapping:
                        arr = d.get(key)
                        if not arr:
                            continue
                        vals = []
                        for it in arr:
                            if isinstance(it, dict):
                                n, v = it.get("label", it.get("value", "")), it.get("value", "")
                            else:
                                n = str(it); v = "" if n == "全部" else n
                            vals.append({"n": n, "v": v})
                        if vals:
                            fl.append({"key": k, "name": name, "value": vals})
                    if fl:
                        result["filters"][tid] = fl
            result["list"] = self._category("2", 1, None)["list"]
        except Exception as e:
            _DIAG["home"] = "except:%s" % e
        if not result["list"]:
            # 首页为空时给出诊断，方便定位 NewBox 环境问题
            info = "build=%s py=%s base=%s err=%s http=%s" % (
                MINO_BUILD, sys.version.split()[0], self.base,
                _DIAG.get("init") or _DIAG.get("home") or "-", _LAST_ERR or "-")
            result["list"] = [{
                "vod_id": "__diag__",
                "vod_name": "【诊断】" + info,
                "vod_remarks": "若见此条说明握手失败",
                "vod_pic": "",
            }]
        return result

    def homeVideoContent(self):
        try:
            r = self._category("2", 1, None)["list"]
            if not r:
                return self.homeContent(False)
            return {"list": r}
        except Exception:
            return {"list": []}

    def _category(self, tid, pg, extend):
        params = {"type_id": str(tid), "page": str(pg), "page_size": str(self._page_size)}
        if extend:
            for k in ("sort", "area", "year", "lang", "class"):
                v = extend.get(k)
                if v and v != "全部":
                    params[k] = v
        j = self._call("GET", "/api/v1/category/videos", params)
        data = j.get("data") or {}
        vlist = []
        for v in data.get("videos") or []:
            vlist.append({
                "vod_id": v.get("vod_id"),
                "vod_name": v.get("vod_name", ""),
                "vod_pic": v.get("vod_pic", ""),
                "vod_remarks": v.get("vod_remarks", "") or v.get("type_name", ""),
            })
        return {"list": vlist}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        try:
            j = self._call("GET", "/api/v1/category/videos",
                           dict({"type_id": str(tid), "page": str(pg), "page_size": str(self._page_size)},
                                **{k: extend[k] for k in ("sort", "area", "year", "lang", "class") if extend.get(k) and extend.get(k) != "全部"}))
            data = j.get("data") or {}
            pg = max(1, pg)
            pagi = data.get("pagination") or {}
            total = pagi.get("total", 0)
            total_pages = pagi.get("total_pages", pg) or pg
            vlist = []
            for v in data.get("videos") or []:
                vlist.append({
                    "vod_id": v.get("vod_id"),
                    "vod_name": v.get("vod_name", ""),
                    "vod_pic": v.get("vod_pic", ""),
                    "vod_remarks": v.get("vod_remarks", "") or v.get("type_name", ""),
                })
            return {"page": pg, "pagecount": total_pages, "limit": self._page_size,
                    "total": total, "list": vlist}
        except Exception:
            return {"page": pg, "pagecount": pg, "limit": self._page_size, "total": 0, "list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        try:
            j = self._call("GET", "/api/v1/search", {"wd": key, "page": str(pg)})
            data = j.get("data") or {}
            vlist = []
            for v in data.get("hits") or []:
                vlist.append({
                    "vod_id": v.get("vod_id"),
                    "vod_name": v.get("vod_name", ""),
                    "vod_pic": v.get("vod_pic", ""),
                    "vod_remarks": v.get("vod_remarks", "") or v.get("type_name", ""),
                })
            return {"page": pg, "pagecount": data.get("total_pages", pg) or pg,
                    "limit": data.get("limit", self._page_size), "total": data.get("total", 0),
                    "list": vlist}
        except Exception:
            return {"page": pg, "pagecount": pg, "limit": self._page_size, "total": 0, "list": []}

    def detailContent(self, array):
        if not array:
            return {"list": []}
        vid = str(array[0]).split(",")[0]
        try:
            j = self._call("GET", "/api/v1/video/detail", {"id": vid})
            data = j.get("data") or {}
            vo = data.get("vod_info") or {}
            lines = vo.get("vod_url_with_player") or []
            play_from, play_url = [], []
            for ln in lines:
                code = ln.get("code") or ""
                name = ln.get("name") or code
                urls = (ln.get("url") or "").split("#")
                eps = []
                for seg in urls:
                    if "$" not in seg:
                        continue
                    title, token = seg.split("$", 1)
                    if not title or not token:
                        continue
                    eps.append("%s$%s|%s" % (title, code, token))
                if eps:
                    play_from.append(name)
                    play_url.append("#".join(eps))
            vod = {
                "vod_id": vid,
                "vod_name": vo.get("vod_name", ""),
                "vod_pic": vo.get("vod_pic", ""),
                "vod_remarks": vo.get("vod_remarks", "") or vo.get("vod_sub", ""),
                "vod_actor": vo.get("vod_actor", ""),
                "vod_director": vo.get("vod_director", ""),
                "vod_year": vo.get("vod_year", ""),
                "vod_area": vo.get("vod_area", ""),
                "vod_class": vo.get("vod_class", "") or vo.get("vod_tag", ""),
                "vod_content": vo.get("vod_blurb", "") or vo.get("vod_content", ""),
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        result = {"parse": 0, "playUrl": "", "url": "", "header": {"User-Agent": UA}}
        try:
            token = id.split("|")[-1] if "|" in id else id
            if not token:
                return result
            j = self._call("POST", "/api/v1/vod/ticket", body=json.dumps({"token": token}, separators=(",", ":")))
            ticket = (j.get("data") or {}).get("ticket", "")
            if not ticket:
                return result
            part = ticket.split(".")[0]
            info = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            d = info.get("data") or {}
            if d.get("enc") == 1 and d.get("payload"):
                raw = _b64d(d["payload"])
                d = json.loads(_aes_gcm_decrypt(self._body_key, raw[:12], raw[12:]).decode("utf-8"))
            url = d.get("url", "")
            parse_api = d.get("parse_api", "")
            parse_secret = d.get("parse_secret", 0)
            if parse_api and int(parse_secret) != 1:
                # url 为加密串，拼接 parse_api 求真实地址
                full = parse_api + quote(url, safe="")
                sp = urlsplit(full)
                q = sp.query
                pr = self._call("GET", sp.path, raw_query=q)
                pd = pr.get("data") or {}
                # parse 接口把真实地址放在顶层 url（部分线路放在 data.url）
                real = pr.get("url") or pd.get("url") or ""
                if str(pr.get("code")) == "200" and real:
                    if int(pr.get("encryption", pd.get("encryption", 0))) != 1:
                        url = real.replace("..", ".")
                        if not url.startswith("http://") and not url.startswith("https://"):
                            url = "https:" + url
                elif str(pr.get("code")) != "200":
                    return result
            if not url:
                try:
                    url = _b64d(url).decode("utf-8")
                except Exception:
                    pass
            if url.startswith("http://") or url.startswith("https://"):
                result["url"] = url
            return result
        except Exception:
            return result

    def localProxy(self, param):
        return None