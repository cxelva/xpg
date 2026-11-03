#!/usr/bin/env python3
# coding=utf-8
"""
禁果短剧 TVBox/影视仓 Python Spider
站点: https://jinguoduanju.app
类型: 短剧 (自定义API，非MacCMS)

API体系:
  设备认证: POST /api/v1/auth/device
  短剧列表: GET /api/v1/dramas?sort=heat|latest&page=1&q=关键词
  短剧详情: GET /api/v1/dramas/{id}
  播放地址: GET /api/v1/episodes/{episodeId}/play

分类模块 (共16个):
  heat(热度), latest(最新), landing(首页推荐)
  nav_all(全部), nav_original(原创精品), nav_single(单体作品)
  nav_anime(动漫改编), nav_movie(影视改编)
  len_multi(多集), len_single(单集)
  tag_mogai(魔改), tag_dushi(都市), tag_zhichang(职场)
  tag_qihuan(奇幻), tag_guzhuang(古装), tag_dongman(动漫)

播放地址: CDN域名 /media/dramas/{id}/episode-{num}-{uuid}/in
需要header: Referer + Origin + X-Forward-Skip-Redirect-Probe
"""
import re
import json
import time
import random
import string
import threading
import requests
from urllib.parse import urljoin, quote

# ==================== 常量 ====================
HOST = "https://jinguoduanju.app"
API_BASE = HOST
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

# 分类模块
MODULES = [
    {"type_id": "heat", "type_name": "热度"},
    {"type_id": "latest", "type_name": "最新"},
    {"type_id": "nav_all", "type_name": "全部"},
    {"type_id": "nav_original", "type_name": "原创精品"},
    {"type_id": "nav_single", "type_name": "单体作品"},
    {"type_id": "nav_anime", "type_name": "动漫改编"},
    {"type_id": "nav_movie", "type_name": "影视改编"},
    {"type_id": "len_multi", "type_name": "多集"},
    {"type_id": "len_single", "type_name": "单集"},
    {"type_id": "tag_mogai", "type_name": "魔改"},
    {"type_id": "tag_dushi", "type_name": "都市"},
    {"type_id": "tag_zhichang", "type_name": "职场"},
    {"type_id": "tag_qihuan", "type_name": "奇幻"},
    {"type_id": "tag_guzhuang", "type_name": "古装"},
    {"type_id": "tag_dongman", "type_name": "动漫"},
]

# 缓存配置
CACHE_TTLS = {
    "list": 300,
    "detail": 180,
    "home": 300,
    "search": 120,
    "play": 60,
}


# ==================== 工具函数 ====================
def _rand_device():
    """生成随机设备ID"""
    hex_chars = "0123456789abcdef"
    return "h5:" + "".join(hex_chars[int(random.random() * 16)] for _ in range(32))


def _clean(text):
    """清洗文本"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _abs_url(base, url):
    """补全相对URL"""
    url = _clean(url)
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    return base.rstrip("/") + "/" + url.lstrip("/")


# ==================== Spider ====================
class Spider:
    def __init__(self):
        self.name = "禁果短剧"
        self.host = HOST
        self.api_base = API_BASE
        self.ua = UA
        self._token = ""
        self._device_id = ""
        self._token_lock = threading.Lock()
        
        # HTTP会话
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=30, pool_maxsize=30)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        
        # 缓存
        self._cache = {}
        self._cache_lock = threading.Lock()
    
    def getDependence(self):
        return []
    
    def destroy(self):
        try:
            self._session.close()
        except Exception:
            pass
    
    # ==================== 认证 ====================
    def _ensure_token(self):
        """确保token有效"""
        if self._token:
            return self._token
        
        with self._token_lock:
            if self._token:
                return self._token
            
            if not self._device_id:
                self._device_id = _rand_device()
            
            url = f"{self.api_base}/api/v1/auth/device"
            payload = {
                "deviceId": self._device_id,
                "channelCode": "",
                "attributionToken": ""
            }
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.ua,
                "Referer": self.host + "/",
                "Origin": self.host,
            }
            
            try:
                r = self._session.post(url, json=payload, headers=headers, timeout=10, verify=False)
                data = r.json()
                self._token = data.get("token", "")
            except Exception:
                pass
            
            return self._token
    
    def _api_get(self, path, params=None):
        """API GET请求"""
        token = self._ensure_token()
        if not token:
            return None
        
        url = f"{self.api_base}/api/v1{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Origin": self.host,
            "Authorization": f"Bearer {token}"
        }
        
        try:
            r = self._session.get(url, params=params, headers=headers, timeout=10, verify=False)
            return r.json()
        except Exception:
            return None
    
    # ==================== 首页 ====================
    def homeContent(self, filter):
        return {"class": MODULES, "filters": {}}
    
    def homeVideoContent(self):
        """首页推荐 - 返回landing模块内容"""
        cache_key = ("home", "landing", 1)
        with self._cache_lock:
            hit = self._cache.get(cache_key)
            if hit and time.time() - hit[0] < CACHE_TTLS["home"]:
                return hit[1]
        
        data = self._api_get("/landing", {"page": 1})
        videos = []
        
        # landing 返回 {"config": {...}, "dramas": [...]}
        if isinstance(data, dict):
            data = data.get("dramas", [])
        
        if isinstance(data, list):
            for item in data:
                vid = str(item.get("id", ""))
                if not vid:
                    continue
                videos.append({
                    "vod_id": "jgdj:" + vid,
                    "vod_name": _clean(item.get("title", "")),
                    "vod_pic": _abs_url(self.host, item.get("coverUrl", "")),
                    "vod_remarks": _clean(item.get("description", "")),
                })
        
        result = {"list": videos}
        with self._cache_lock:
            self._cache[cache_key] = (time.time(), result)
        return result
    
    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
        except Exception:
            page = 1
        
        tid = str(tid)
        
        # 构建请求参数
        params = {"page": page}
        sort = ""
        
        # 热度/最新排序
        if tid == "heat":
            sort = "heat"
        elif tid == "latest":
            sort = "latest"
        
        if sort:
            params["sort"] = sort
        
        # 标签过滤
        tag_map = {
            "tag_mogai": "魔改",
            "tag_dushi": "都市",
            "tag_zhichang": "职场",
            "tag_qihuan": "奇幻",
            "tag_guzhuang": "古装",
            "tag_dongman": "动漫",
        }
        if tid in tag_map:
            params["_tagFilter"] = tag_map[tid]
        
        # 调用API
        data = self._api_get("/dramas", params)
        if not isinstance(data, list):
            data = []
        
        # 转换为视频列表
        videos = []
        seen = set()
        for item in data:
            vid = str(item.get("id", ""))
            if not vid or vid in seen:
                continue
            seen.add(vid)
            videos.append({
                "vod_id": "jgdj:" + vid,
                "vod_name": _clean(item.get("title", "")),
                "vod_pic": _abs_url(self.host, item.get("coverUrl", "")),
                "vod_remarks": _clean(item.get("description", "")),
            })
        
        return {
            "page": page,
            "pagecount": page + 1,
            "limit": len(videos),
            "total": len(videos) + (page - 1) * 24,
            "list": videos,
        }
    
    # ==================== 详情 ====================
    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        
        raw_id = _clean(ids)
        if not raw_id:
            return {"list": []}
        
        # 解析ID: jgdj:123 或 123
        drama_id = raw_id.replace("jgdj:", "").split(":")[0]
        
        cache_key = ("detail", drama_id)
        with self._cache_lock:
            hit = self._cache.get(cache_key)
            if hit and time.time() - hit[0] < CACHE_TTLS["detail"]:
                return hit[1]
        
        data = self._api_get(f"/dramas/{drama_id}")
        if not data:
            return {"list": []}
        
        drama = data.get("drama", {})
        episodes = data.get("episodes", [])
        
        # 构建播放列表
        play_from = "禁果短剧"
        play_urls = []
        for i, ep in enumerate(episodes):
            ep_num = ep.get("number", i + 1)
            ep_id = ep.get("id", "")
            ep_title = _clean(ep.get("title", f"第{ep_num}集"))
            ep_link = f"jgdj:{drama_id}:{ep_num}:{ep_id}"
            play_urls.append(f"{ep_title}${ep_link}")
        
        vod = {
            "vod_id": "jgdj:" + drama_id,
            "vod_name": _clean(drama.get("title", "")),
            "vod_pic": _abs_url(self.host, drama.get("coverUrl", "")),
            "vod_content": _clean(data.get("description", "")),
            "vod_play_from": play_from,
            "vod_play_url": "#".join(play_urls) if play_urls else "",
        }
        
        result = {"list": [vod]}
        with self._cache_lock:
            self._cache[cache_key] = (time.time(), result)
        return result
    
    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
        except Exception:
            page = 1
        
        keyword = _clean(key)
        if not keyword:
            return {"list": [], "page": page, "pagecount": page, "limit": 0, "total": 0}
        
        data = self._api_get("/dramas", {"sort": "latest", "q": keyword, "page": page})
        if not isinstance(data, list):
            data = []
        
        videos = []
        seen = set()
        for item in data:
            vid = str(item.get("id", ""))
            if not vid or vid in seen:
                continue
            seen.add(vid)
            videos.append({
                "vod_id": "jgdj:" + vid,
                "vod_name": _clean(item.get("title", "")),
                "vod_pic": _abs_url(self.host, item.get("coverUrl", "")),
                "vod_remarks": _clean(item.get("description", "")),
            })
        
        return {
            "page": page,
            "pagecount": page + 1 if len(videos) >= 20 else page,
            "limit": len(videos),
            "total": len(videos) + (page - 1) * 20,
            "list": videos,
        }
    
    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        play_path = _clean(id)
        if not play_path:
            return {"parse": 1, "url": "", "header": {}}
        
        # 解析链接格式: jgdj:{dramaId}:{epNum}:{episodeId}
        parts = play_path.replace("jgdj:", "").split(":")
        if len(parts) < 3:
            return {"parse": 1, "url": play_path, "header": {}}
        
        drama_id = parts[0]
        ep_num = parts[1]
        episode_id = parts[2]
        
        # 获取播放地址
        data = self._api_get(f"/episodes/{episode_id}/play")
        if not data:
            return {"parse": 1, "url": play_path, "header": {}}
        
        video_url = _clean(data.get("videoUrl", ""))
        if not video_url:
            return {"parse": 1, "url": play_path, "header": {}}
        
        # 补全URL
        video_url = _abs_url(self.host, video_url)
        
        # 返回播放地址和必要的header
        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": video_url,
            "header": {
                "User-Agent": self.ua,
                "Referer": self.host + "/",
                "Origin": self.host,
                "X-Forward-Skip-Redirect-Probe": "1",
            },
        }
    
    # ==================== 其他接口 ====================
    def isVideoFormat(self, url):
        if not url:
            return False
        url = url.lower()
        return any(ext in url for ext in [".m3u8", ".mp4", ".flv", ".ts", ".mkv"])
    
    def manualVideoCheck(self):
        return True
    
    def localProxy(self, param):
        return [404, "text/plain", b"", {}]
    
    def getName(self):
        return self.name
    
    def action(self, action):
        return {}
    
    def init(self, extend=""):
        if extend:
            ext = _clean(extend)
            if ext.startswith("{"):
                try:
                    d = json.loads(ext)
                    self.host = str(d.get("host", self.host)).rstrip("/")
                    self.api_base = self.host
                except Exception:
                    pass


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    print(f"站点: {spider.name}")
    print(f"分类数: {len(MODULES)}")
    print(f"Token: {spider._ensure_token()[:20]}...")
