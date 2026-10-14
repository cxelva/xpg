# -*- coding: utf-8 -*-
"""
极光影视 - hellociqryx6e.com
Next.js SPA 站点，数据全部走异步 JSON 接口（非服务端渲染），需签名。

关键结论（已实测验证）：
1. 接口前缀 /api/mw-movie，业务接口在 /anonymous/** 下。
2. 请求签名（前端 webpack 模块 5055/49858 中提取）：
   sign = SHA1( MD5( 待签串 ) )
   - GET ：待签串 = 参数按 key 升序拼成 "k=v&k=v"（过滤空值）+ "&key={KEY}&t={ms}"
   - 无参数：待签串 = "key={KEY}&t={ms}"
   - 其中 KEY = cb808529bae6b6be45ecfab29a4889bc，t 为毫秒时间戳
   请求头需带：sign / t / deviceId / client-type
3. 核心接口：
   - 分类  /anonymous/get/filer/type            无参
   - 列表  /anonymous/video/list                 pageNum, pageSize, type1[, type2]
   - 搜索  /anonymous/video/searchByWord         pageNum, pageSize, keyword
   - 详情  /anonymous/video/detail               id                 -> episodeList[{nid,name,sort}]
   - 播放  /anonymous/v2/video/episode/url       id, nid            -> list[{resolution,url,...}]
   播放接口返回真实 m3u8 直链（带 auth_key，有时效，需实时取，不做长期缓存）。
"""
import re
import json
import time
import uuid
import hashlib
import requests

try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def __init__(self):
            pass


class Spider(Spider):
    # ==================== 基础配置 ====================
    name = "极光影视"
    base_url = "https://hellociqryx6e.com"
    api_prefix = "/api/mw-movie"
    sign_key = "cb808529bae6b6be45ecfab29a4889bc"

    searchable = 1
    quickSearch = 1
    filterable = 1

    # 分类（typeId -> 名称），体育直播(ID=7)非点播，不纳入
    class_name = ["电影", "电视剧", "综艺", "动漫", "短剧"]
    class_url = ["1", "2", "3", "4", "88"]
    CATEGORY_NAMES = {
        "1": "电影", "2": "电视剧", "3": "综艺", "4": "动漫", "88": "短剧",
    }

    # 子类筛选（ti=电影/电视剧/综艺/动漫 的题材），来自 /anonymous/v1/get/filer/list
    FILTERS = {
        "1": [("22", "喜剧"), ("23", "动作"), ("30", "科幻"), ("26", "爱情"),
              ("27", "悬疑"), ("87", "奇幻"), ("37", "剧情"), ("28", "恐怖"),
              ("29", "战争"), ("31", "犯罪"), ("34", "动画"), ("35", "纪录片")],
        "2": [("48", "国产剧"), ("49", "香港剧"), ("50", "韩国剧"), ("51", "欧美剧"),
              ("52", "台湾剧"), ("53", "日本剧"), ("54", "海外剧"), ("55", "泰国剧")],
        "3": [("64", "国内综艺"), ("65", "国外综艺")],
        "4": [("69", "国产动漫"), ("70", "日韩动漫"), ("71", "欧美动漫"), ("72", "港台动漫")],
        "88": [("75", "短剧")],
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "client-type": "2",
        "Referer": "https://hellociqryx6e.com/",
    }

    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://hellociqryx6e.com/",
        "Accept": "*/*",
    }

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._device_id = str(uuid.uuid4())
        self._play_cache = {}
        self._cache_ttl = 300          # 播放直链有时效，缓存 5 分钟
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

    # ==================== 签名 ====================
    @staticmethod
    def _filter_empty(params):
        out = {}
        for k, v in (params or {}).items():
            if v is None or v == "" or v == "undefined" or v == "null":
                continue
            out[k] = v
        return out

    def _sign_headers(self, params, method="GET"):
        params = self._filter_empty(params)
        t = str(int(time.time() * 1000))
        if params:
            if method.upper() == "GET":
                param_str = "&".join("%s=%s" % (k, params[k]) for k in sorted(params))
            else:
                param_str = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            raw = "%s&key=%s&t=%s" % (param_str, self.sign_key, t)
        else:
            raw = "key=%s&t=%s" % (self.sign_key, t)
        md5_hex = hashlib.md5(raw.encode("utf-8")).hexdigest()
        sign = hashlib.sha1(md5_hex.encode("utf-8")).hexdigest()
        headers = {
            "sign": sign,
            "t": t,
            "deviceId": self._device_id,
            "client-type": "2",
        }
        return headers, params

    # ==================== 请求封装 ====================
    def _apply_req_delay(self):
        now = time.time()
        elapsed = now - self._last_req_time
        if 0 < elapsed < self._min_req_interval:
            time.sleep(self._min_req_interval - elapsed)
        self._last_req_time = time.time()

    def _get_json(self, path, params=None, max_retry=2, timeout=15):
        url = self.base_url + self.api_prefix + path
        for attempt in range(max_retry):
            try:
                self._apply_req_delay()
                headers, p = self._sign_headers(params or {}, "GET")
                headers.update(self.headers)
                resp = self._session.get(url, headers=headers, params=p, timeout=timeout)
                data = resp.json()
                if data.get("code") == 200:
                    return data.get("data")
                self._log("接口异常 %s: %s" % (path, data.get("msg")))
                return None
            except Exception as e:
                self._log("请求失败 %s (%s/%s): %s" % (path, attempt + 1, max_retry, e))
                if attempt < max_retry - 1:
                    time.sleep(0.8 + attempt)
        return None

    # ==================== 列表解析 ====================
    def _parse_item(self, it):
        vod_id = str(it.get("vodId"))
        name = it.get("vodName") or ""
        remarks = it.get("vodRemarks") or ""
        if not remarks:
            remarks = it.get("vodVersion") or ""
        if not remarks:
            remarks = it.get("vodSerial") or ""
        return {
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": it.get("vodPic") or "",
            "vod_remarks": remarks,
        }

    # ==================== TVBox 核心方法 ====================
    def init(self, extend=''):
        self._log("初始化完成 signKey=%s" % self.sign_key)

    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": tid, "type_name": name}
                for tid, name in self.CATEGORY_NAMES.items()
            ]
        }
        if filter:
            filters = {}
            for tid, opts in self.FILTERS.items():
                filters[tid] = [{
                    "key": "type2",
                    "name": "类型",
                    "value": [{"n": n, "v": v} for v, n in opts],
                }]
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        try:
            data = self._get_json("/anonymous/video/list", {"pageNum": 1, "pageSize": 30, "type1": 1})
            lst = (data or {}).get("list") or []
            return {"list": [self._parse_item(x) for x in lst]}
        except Exception as e:
            self._log("homeVideoContent异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            if str(tid) not in self.CATEGORY_NAMES:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            params = {"pageNum": pg, "pageSize": 24, "type1": int(tid)}
            # 筛选子类
            if content and isinstance(content, dict) and content.get("type2"):
                params["type2"] = content["type2"]
            self._log("分类请求: type1=%s pg=%s" % (tid, pg))
            data = self._get_json("/anonymous/video/list", params)
            if not data:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
            videos = [self._parse_item(x) for x in (data.get("list") or [])]
            total_page = data.get("totalPage") or 1
            total = data.get("totalCount") or 0
            return {
                "list": videos,
                "page": pg,
                "pagecount": total_page,
                "limit": 24,
                "total": total,
            }
        except Exception as e:
            self._log("categoryContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        pg = max(1, int(pg or 1))
        keyword = str(key or "").strip()
        if not keyword:
            return {"page": pg, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        try:
            params = {"pageNum": pg, "pageSize": 24, "keyword": keyword}
            self._log("搜索请求: %s pg=%s" % (keyword, pg))
            data = self._get_json("/anonymous/video/searchByWord", params)
            result = (data or {}).get("result") or {}
            lst = result.get("list") or []
            videos = [self._parse_item(x) for x in lst]
            if not quick:
                key_lower = keyword.lower()

                def _score(v):
                    name = (v.get("vod_name") or "").lower()
                    if name == key_lower:
                        return 0
                    if name.startswith(key_lower):
                        return 1
                    if key_lower in name:
                        return 2
                    return 3
                videos = sorted(videos, key=_score)
            return {
                "list": videos,
                "page": pg,
                "pagecount": result.get("totalPage") or 1,
                "limit": 24,
                "total": result.get("totalCount") or 0,
            }
        except Exception as e:
            self._log("searchContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            vod_id = str(vod_id).split("-")[0]
            self._log("详情请求: %s" % vod_id)
            d = self._get_json("/anonymous/video/detail", {"id": vod_id})
            if not d:
                return {"list": []}

            vod_name = d.get("vodName") or "未知"
            eps = d.get("episodeList") or []
            if not eps:
                self._log("无播放源")
                return {"list": []}

            # 单线路：集数按 sort 排序，链接用 "vodId-nid"
            eps_sorted = sorted(eps, key=lambda x: x.get("sort") or 0)
            ep_items = []
            for ep in eps_sorted:
                ep_name = ep.get("name") or str(ep.get("sort") or "")
                link = "%s-%s" % (vod_id, ep.get("nid"))
                ep_items.append("%s$%s" % (ep_name, link))

            # 线路名：电影多为"蓝光"，剧集多为"线路1"
            is_movie = str(d.get("typeId1")) == "1" and len(eps_sorted) <= 1
            source_name = "蓝光" if is_movie else "线路1"

            vod_play_url = "#".join(ep_items)

            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": d.get("vodPic") or "",
                "vod_year": str(d.get("vodYear") or ""),
                "vod_area": d.get("vodArea") or "",
                "vod_actor": d.get("vodActor") or "",
                "vod_director": d.get("vodDirector") or "",
                "vod_content": self._clean_html(d.get("vodContent") or ""),
                "vod_remarks": d.get("vodRemarks") or d.get("vodVersion") or "",
                "vod_play_from": source_name,
                "vod_play_url": vod_play_url,
            }
            self._log("详情解析成功: %s 集数: %d" % (vod_name, len(ep_items)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent异常: %s" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = str(id).split("-")
            if len(parts) != 2:
                return {"parse": 0, "url": "", "header": ""}
            vod_id, nid = parts
            cache_key = "%s-%s" % (vod_id, nid)
            now = time.time()
            if cache_key in self._play_cache:
                url, ts = self._play_cache[cache_key]
                if now - ts < self._cache_ttl:
                    return {"parse": 0, "url": url, "header": self.play_headers.copy()}

            data = self._get_json("/anonymous/v2/video/episode/url", {"id": vod_id, "nid": nid})
            play_url = ""
            if data:
                urls = data.get("list") or []
                # 优先取分辨率最高的一条
                urls = [u for u in urls if u.get("url")]
                urls.sort(key=lambda u: u.get("resolution") or 0, reverse=True)
                if urls:
                    play_url = urls[0]["url"]
            if not play_url:
                return {"parse": 0, "url": "", "header": ""}

            self._play_cache[cache_key] = (play_url, now)
            is_direct = bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', play_url, re.I))
            self._log("播放URL: %s... parse=%d" % (play_url[:80], 0 if is_direct else 1))
            if is_direct:
                return {"parse": 0, "url": play_url, "header": self.play_headers.copy()}
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
