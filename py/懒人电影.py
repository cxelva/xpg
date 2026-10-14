# -*- coding: utf-8 -*-
"""
懒人电影 - lanrendy.top
自研 SPA 前端 + JSON API（数据源 360zy / MacCMS 字段），无页面级反爬（curl 直连可访问）。

关键结论（已实测验证）：
1. 数据接口：GET /api/at/json  （JSON，UTF-8，返回 MacCMS 全字段）
   - 列表/搜索：ac=videolist&pg=1[&t=子分类][&wd=关键词][&year=年份]
       每页固定 20 条；父分类（t=1/2/3/4/17）返回 0 条，必须聚合子分类；t=46 短剧例外有数据
   - 详情：ac=detail&ids={vod_id} → {vod_play_from/vod_play_url/type_name/...}
2. 分类（type_id 表，来自站点 NAV）：
   电影(父1): 6动作 7喜剧 8爱情 9科幻 10恐怖 11剧情 12战争 20惊悚 21家庭 22古装 23历史
             24悬疑 25犯罪 26灾难 27纪录 28短片 29动画 45西部
   连续剧(父2): 13国产 14香港 15韩国 16欧美 30台湾 31日本 32海外 33泰国
   综艺(父3): 34大陆 35港台 36日韩 37欧美
   动漫(父4): 38国产 39欧美 40日韩
   短剧(父46): 47都市 48悬疑 49穿越 50仙侠 51反转 52恋爱 53逆袭（父 46 直接有数据）
   体育(父17): 18NBA 41足球 42篮球
3. 播放：详情 vod_play_url 为 MacCMS 格式  name$url#集2$url...$$$线路2...
   直链为 m3u8（vod1.maowushi.com 等），带 Referer https://lanrendy.top/ 可直接访问；
   站点自带 /v/m3u8?u= 内嵌代理兜底（直连失败时可用，耗站点请求次数）
4. 封面：doubanio/qpic/iqiyipic 等防盗链图床，站点用 /img?u= 代理；壳子默认透传原图
"""
import re
import json
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

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

    # 父分类（type_id, 名称, 子分类列表）；父分类需聚合子分类取数
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
        self._play_cache = {}
        self._cache_ttl = 1800
        self._re_direct = re.compile(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', re.I)

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

    def _clean_name(self, name):
        """片名清洗（去尾部垃圾后缀 + 压缩空白）"""
        if not name:
            return name
        name = re.sub(
            r'[\s\-_]*(?:HD|TC|TS|V|枪版|DVD|BD|1080P|720P|4K|2K|高清|超清|蓝光|'
            r'国语|粤语|中字|中英双字|完整版|全集|未删减版|(?:第[0-9一二三四五六七八九十]+[集季期]))\s*$',
            "", str(name), flags=re.I)
        return re.sub(r'\s+', ' ', name).strip()

    # ==================== 网络层（requests → urllib 双通道） ====================
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

    def _raw(self, url, method="GET", body=None, headers=None, timeout=12):
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

    def _api(self, params, retry=2):
        """调 JSON API，失败重试"""
        url = self.base_url + "/api/at/json?" + "&".join(
            "%s=%s" % (k, urllib.parse.quote(str(v))) for k, v in params.items())
        headers = {
            "User-Agent": self.UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.base_url + "/",
        }
        for attempt in range(retry):
            status, text = self._raw(url, headers=headers, timeout=12)
            if status == 200 and text:
                try:
                    return json.loads(text)
                except Exception:
                    pass
            if attempt < retry - 1:
                time.sleep(0.8 + attempt)
        return None

    # ==================== 列表处理 ====================
    def _norm_video(self, v):
        """API 条目 → TVBox 列表项"""
        return {
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": self._clean_name(v.get("vod_name", "")),
            "vod_pic": v.get("vod_pic") or "",
            "vod_remarks": v.get("vod_remarks") or v.get("type_name") or "",
        }

    def _category_aggregate(self, subs, pg, year=None):
        """父分类：并发拉子分类第 pg 页，合并去重取前 60"""
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = [ex.submit(self._fetch_list, {"t": t, "pg": pg, "year": year}) for t in subs]
                groups = [f.result() for f in futs]
        except Exception:
            groups = [self._fetch_list({"t": t, "pg": pg, "year": year}) for t in subs]
        return self._merge(groups)

    def _fetch_list(self, params):
        p = {"ac": "videolist"}
        for k, v in params.items():
            if v:
                p[k] = v
        j = self._api(p)
        if not j:
            return []
        return [self._norm_video(v) for v in (j.get("list") or [])]

    def _merge(self, groups, limit=60):
        """多组结果按 vod_id 去重、vod_time 倒序，截取前 limit 条"""
        seen = {}
        out = []
        for g in groups:
            for v in g:
                vid = v.get("vod_id", "")
                if vid and vid not in seen:
                    seen[vid] = 1
                    out.append(v)
        out.sort(key=lambda x: x.get("vod_time") or "", reverse=True)
        return out[:limit]

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
        result = {
            "class": [
                {"type_id": cid, "type_name": cname}
                for cid, cname, _subs in self.CATEGORY
            ]
        }
        if filter:
            result["filters"] = {}
            result["filter"] = {}
        return result

    def homeVideoContent(self):
        try:
            # 首页行 = 最新电影(t=11) + 最新剧集(t=13) + 动漫(t=38)，合并去重
            groups = [
                self._fetch_list({"t": 11, "pg": 1}),
                self._fetch_list({"t": 13, "pg": 1}),
                self._fetch_list({"t": 38, "pg": 1}),
            ]
            return {"list": self._merge(groups, limit=30)}
        except Exception as e:
            self._log("homeVideoContent异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            year = ""
            if content:
                try:
                    year = str((json.loads(content) or {}).get("year") or "")
                except Exception:
                    year = ""
            # 父分类聚合；短剧(46)上游直接有数据，特例单请求
            if str(tid) == "46":
                lst = self._fetch_list({"t": 46, "pg": pg, "year": year})
            else:
                subs = self.SUBS_MAP.get(str(tid))
                if not subs:
                    return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
                lst = self._category_aggregate(subs, pg, year)
            if not lst:
                lst = []
            return {
                "list": lst,
                "page": pg,
                "pagecount": 1,
                "limit": 24,
                "total": 0,
            }
        except Exception as e:
            self._log("categoryContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            keyword = str(key or "").strip()
            if not keyword:
                return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
            lst = self._fetch_list({"wd": keyword, "pg": 1})
            return {
                "list": lst,
                "page": 1,
                "pagecount": 1,
                "limit": 24,
                "total": len(lst),
            }
        except Exception as e:
            self._log("searchContent异常: %s" % e)
            return {"list": []}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            j = self._api({"ac": "detail", "ids": vod_id})
            if not j:
                return {"list": []}
            v = (j.get("list") or [])[0]
            if not v:
                return {"list": []}
            vod_name = self._clean_name(v.get("vod_name", ""))
            video = {
                "vod_id": str(v.get("vod_id", vod_id)),
                "vod_name": vod_name,
                "vod_pic": v.get("vod_pic") or "",
                "vod_year": v.get("vod_year") or "",
                "vod_area": v.get("vod_area") or "",
                "vod_actor": v.get("vod_actor") or "",
                "vod_director": v.get("vod_director") or "",
                "vod_content": self._clean(v.get("vod_content")),
                "vod_remarks": v.get("vod_remarks") or "",
                "vod_play_from": v.get("vod_play_from") or "",
                "vod_play_url": v.get("vod_play_url") or "",
            }
            if not video["vod_play_url"]:
                self._log("无可播资源: %s" % vod_name)
                return {"list": []}
            self._log("详情解析成功: %s 线路: %s" % (
                vod_name, video["vod_play_from"]))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent异常: %s" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = str(id or "").strip()
            if not url:
                return {"parse": 0, "url": "", "header": ""}
            # m3u8/mp4 等直链 → 直连播放（带站点 Referer）；其余交给壳子解析
            if self._re_direct.search(url):
                return {
                    "parse": 0,
                    "url": url,
                    "header": {
                        "User-Agent": self.UA,
                        "Referer": self.base_url + "/",
                    },
                }
            return {"parse": 1, "url": url, "header": ""}
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