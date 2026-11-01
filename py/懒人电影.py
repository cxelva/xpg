# -*- coding: utf-8 -*-
"""
懒人电影 - lanrendy.top
自研 SPA 前端 + JSON API（数据源 360zy / MacCMS 字段），无页面级反爬。

关键结论（2026-11 实测）：
1. 接口：GET /api/at/json
   - 列表：ac=videolist&pg=1[&t=分类][&wd=关键词][&year=年份]  每页20条
   - 详情：ac=detail&ids={vod_id}
   - 父分类 t=1/2/3/4/17 返回0条，必须聚合子分类；t=46 短剧父分类直接有数据
2. 播放：vod_play_url 为 name$url#...$$$线路2...，直链 m3u8，带 Referer 可播
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
    name = "懒人电影"
    site_url = "https://lanrendy.top"
    base_url = "https://lanrendy.top"
    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

    # 父分类 (type_id, 名称, 子分类列表)
    CATEGORY = [
        ("1", "电影", ["6", "7", "8", "9", "10", "11", "12", "20", "21",
                       "22", "23", "24", "25", "26", "27", "28", "29", "45"]),
        ("2", "连续剧", ["13", "14", "15", "16", "30", "31", "32", "33"]),
        ("3", "综艺", ["34", "35", "36", "37"]),
        ("4", "动漫", ["38", "39", "40"]),
        ("46", "短剧", ["47", "48", "49", "50", "51", "52", "53"]),
        ("17", "体育", ["18", "41", "42"]),
    ]
    CATEGORY_MAP = {c[0]: c[1] for c in CATEGORY}
    SUBS_MAP = {c[0]: c[2] for c in CATEGORY}

    def __init__(self):
        super().__init__()
        self._http = None
        self._urllib_opener = None
        self._re_direct = re.compile(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', re.I)

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

    def _clean_name(self, name):
        if not name:
            return name
        name = re.sub(
            r'[\s\-_]*(?:HD|TC|TS|V|枪版|DVD|BD|1080P|720P|4K|2K|高清|超清|蓝光|'
            r'国语|粤语|中字|中英双字|完整版|全集|未删减版|(?:第[0-9一二三四五六七八九十]+[集季期]))\s*$',
            "", str(name), flags=re.I)
        return re.sub(r'\s+', ' ', name).strip()

    # ==================== 网络 ====================
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
                handlers = [
                    urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(context=ctx),
                ]
                self._urllib_opener = urllib.request.build_opener(*handlers)
            except Exception:
                self._urllib_opener = None

    def _raw(self, url, method="GET", body=None, headers=None, timeout=12):
        self._init_http()
        headers = dict(headers or {})
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.UA

        if self._http is not None:
            try:
                if method == "GET":
                    r = self._http.get(url, headers=headers, timeout=timeout)
                else:
                    r = self._http.post(url, data=body, headers=headers, timeout=timeout)
                return r.status_code, r.text
            except Exception as e:
                self._log("requests失败: %s" % e)

        if self._urllib_opener is not None:
            try:
                data = body.encode("utf-8") if body and method == "POST" else None
                req = urllib.request.Request(url, data=data, headers=headers)
                req.get_method = lambda: method
                resp = self._urllib_opener.open(req, timeout=timeout)
                return resp.getcode(), resp.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                try:
                    return e.code, e.read().decode("utf-8", "ignore")
                except Exception:
                    return getattr(e, "code", 0), ""
            except Exception as e:
                self._log("urllib失败: %s" % e)
        return 0, ""

    def _api(self, params, retry=2):
        qs = "&".join(
            "%s=%s" % (k, urllib.parse.quote(str(v), safe=""))
            for k, v in params.items()
            if v is not None and str(v) != ""
        )
        url = self.base_url + "/api/at/json?" + qs
        headers = {
            "User-Agent": self.UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.base_url + "/",
            "Origin": self.base_url,
        }
        for attempt in range(retry):
            status, text = self._raw(url, headers=headers, timeout=12)
            if status == 200 and text:
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
            if attempt < retry - 1:
                time.sleep(0.5 + attempt * 0.3)
        return None

    # ==================== 列表 ====================
    def _norm_video(self, v):
        return {
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": self._clean_name(v.get("vod_name", "")),
            "vod_pic": v.get("vod_pic") or "",
            "vod_remarks": v.get("vod_remarks") or v.get("type_name") or "",
            "vod_time": v.get("vod_time") or "",
            "vod_year": v.get("vod_year") or "",
        }

    def _fetch_list(self, params):
        p = {"ac": "videolist"}
        for k, v in params.items():
            if v is not None and str(v) != "":
                p[k] = v
        j = self._api(p)
        if not j or not isinstance(j, dict):
            return []
        return [self._norm_video(v) for v in (j.get("list") or []) if v]

    def _merge(self, groups, limit=60):
        seen = set()
        out = []
        for g in groups:
            if not g:
                continue
            for v in g:
                vid = v.get("vod_id", "")
                if vid and vid not in seen:
                    seen.add(vid)
                    out.append(v)
        out.sort(key=lambda x: x.get("vod_time") or "", reverse=True)
        return out[:limit]

    def _category_aggregate(self, subs, pg, year=None):
        """串行拉取子分类（兼容无 concurrent.futures / 线程受限的环境）"""
        if not subs:
            return []
        groups = []
        for t in subs:
            try:
                lst = self._fetch_list({"t": t, "pg": pg, "year": year})
                if lst:
                    groups.append(lst)
            except Exception as e:
                self._log("子分类 t=%s 失败: %s" % (t, e))
            time.sleep(0.06)
        return self._merge(groups, limit=60)

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
            self._log("init异常: %s" % e)

    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": cid, "type_name": cname}
                for cid, cname, _ in self.CATEGORY
            ]
        }
        if filter:
            years = [{"n": "全部", "v": ""}]
            for y in range(2026, 2015, -1):
                years.append({"n": str(y), "v": str(y)})
            result["filters"] = {
                cid: [{"key": "year", "name": "年份", "value": years}]
                for cid, _, _ in self.CATEGORY
            }
        return result

    def homeVideoContent(self):
        try:
            groups = [
                self._fetch_list({"t": "11", "pg": "1"}),
                self._fetch_list({"t": "13", "pg": "1"}),
                self._fetch_list({"t": "38", "pg": "1"}),
            ]
            lst = self._merge(groups, limit=30)
            self._log("homeVideo 返回 %d 条" % len(lst))
            return {"list": lst}
        except Exception as e:
            self._log("homeVideo异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            year = ""
            if content:
                try:
                    if isinstance(content, str):
                        content = json.loads(content) if content.strip() else {}
                    year = str((content or {}).get("year") or "")
                except Exception:
                    year = ""
            tid = str(tid)

            if tid == "46":
                lst = self._fetch_list({"t": "46", "pg": pg, "year": year})
            else:
                subs = self.SUBS_MAP.get(tid)
                if not subs:
                    lst = self._fetch_list({"t": tid, "pg": pg, "year": year})
                else:
                    lst = self._category_aggregate(subs, pg, year)

            if not lst:
                lst = []
            pagecount = 80 if tid == "46" else 40
            self._log("category tid=%s pg=%s -> %d条" % (tid, pg, len(lst)))
            return {
                "list": lst,
                "page": pg,
                "pagecount": pagecount,
                "limit": 24,
                "total": 0,
            }
        except Exception as e:
            self._log("category异常: %s" % e)
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            keyword = str(key or "").strip()
            if not keyword:
                return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
            lst = self._fetch_list({"wd": keyword, "pg": 1})
            self._log("search '%s' -> %d条" % (keyword, len(lst)))
            return {
                "list": lst,
                "page": 1,
                "pagecount": 1,
                "limit": 24,
                "total": len(lst),
            }
        except Exception as e:
            self._log("search异常: %s" % e)
            return {"list": []}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            j = self._api({"ac": "detail", "ids": vod_id})
            if not j:
                return {"list": []}
            lst = j.get("list") or []
            if not lst:
                return {"list": []}
            v = lst[0]
            vod_name = self._clean_name(v.get("vod_name", ""))
            play_from = v.get("vod_play_from") or ""
            play_url = v.get("vod_play_url") or ""
            video = {
                "vod_id": str(v.get("vod_id", vod_id)),
                "vod_name": vod_name,
                "vod_pic": v.get("vod_pic") or "",
                "vod_year": v.get("vod_year") or "",
                "vod_area": v.get("vod_area") or "",
                "vod_actor": v.get("vod_actor") or "",
                "vod_director": v.get("vod_director") or "",
                "vod_content": self._clean(v.get("vod_content") or v.get("vod_blurb") or ""),
                "vod_remarks": v.get("vod_remarks") or "",
                "vod_play_from": play_from,
                "vod_play_url": play_url,
            }
            if not play_url:
                self._log("无播放源: %s" % vod_name)
                return {"list": []}
            self._log("详情OK: %s 线路:%s" % (vod_name, play_from))
            return {"list": [video]}
        except Exception as e:
            self._log("detail异常: %s" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = str(id or "").strip()
            if not url:
                return {"parse": 0, "url": "", "header": {}}
            if self._re_direct.search(url):
                return {
                    "parse": 0,
                    "url": url,
                    "header": {
                        "User-Agent": self.UA,
                        "Referer": self.base_url + "/",
                        "Origin": self.base_url,
                    },
                }
            return {"parse": 1, "url": url, "header": {}}
        except Exception as e:
            self._log("player异常: %s" % e)
            return {"parse": 0, "url": "", "header": {}}

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        return bool(self._re_direct.search(str(url or "")))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._http = None
        self._urllib_opener = None

    def localProxy(self, param):
        return None
