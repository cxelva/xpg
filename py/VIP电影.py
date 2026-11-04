# -*- coding: utf-8 -*-
"""
VIP电影 TVBox/猫影视爬虫插件 — https://www.vipdy.vip
MacCMS v10 (JB模板) + HTML解析 + JSON搜索接口

接口说明:
  分类列表     /s/{slug}-----------.html
  筛选参数     /s/{slug}-{area}-{order}-{year}-{page}.html
  搜索联想     /index.php/ajax/suggest?mid=1&wd={kw}&limit=20&page={page}
  搜索结果     /sou/{kw}------------.html
  详情页       /v/{id}.html
  播放页       /p/{id}-{sid}-{nid}.html
  播放数据     var player_aaaa={"url":"真实m3u8地址","from":"线路名",...}
"""

import re
import json
import time
import warnings
import threading
from urllib.parse import quote, unquote

try:
    warnings.filterwarnings("ignore")
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    from requests.adapters import HTTPAdapter

    class Spider:
        def __init__(self):
            self._session = _rq.Session()
            adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)

        def fetch(self, url, headers=None, timeout=15, **kw):
            headers = headers or {}
            headers.setdefault("User-Agent", UA)
            return self._session.get(url, headers=headers, timeout=timeout, verify=False, **kw)

        def destroy(self):
            try:
                self._session.close()
            except Exception:
                pass


HOST = "https://www.vipdy.vip"
UA = ("Mozilla/5.0 (Linux; Android 12; M2007J22C) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

# 一级分类
CLASSES = [
    {"type_name": "电影", "type_id": "dianying"},
    {"type_name": "剧集", "type_id": "juji"},
    {"type_name": "综艺", "type_id": "zongyi"},
    {"type_name": "动漫", "type_id": "dongman"},
    {"type_name": "体育", "type_id": "tiyu"},
]

# 二级分类 (按一级分类分组)
SUB_CLASSES = {
    "dianying": [
        {"n": "动作片", "v": "dongzuopian"},
        {"n": "喜剧片", "v": "xijupian"},
        {"n": "爱情片", "v": "aiqingpian"},
        {"n": "科幻片", "v": "kehuanpian"},
        {"n": "剧情片", "v": "juqingpian"},
        {"n": "恐怖片", "v": "kongbupian"},
        {"n": "奇幻片", "v": "qihuanpian"},
        {"n": "战争片", "v": "zhanzhengpian"},
        {"n": "记录片", "v": "jilupian"},
        {"n": "福利片", "v": "fulipian"},
        {"n": "动画片", "v": "donghuapian"},
    ],
    "juji": [
        {"n": "国产剧", "v": "guochanju"},
        {"n": "港台剧", "v": "gangtaiju"},
        {"n": "日韩剧", "v": "rihanju"},
        {"n": "欧美剧", "v": "oumeiju"},
        {"n": "海外剧", "v": "haiwaiju"},
        {"n": "短剧", "v": "duanju"},
    ],
    "zongyi": [
        {"n": "大陆综艺", "v": "daluzongyi"},
        {"n": "港台综艺", "v": "gangtaizongyi"},
        {"n": "日韩综艺", "v": "rihanzongyi"},
        {"n": "欧美综艺", "v": "oumeizongyi"},
    ],
    "dongman": [
        {"n": "国产动漫", "v": "guochandongman"},
        {"n": "港台动漫", "v": "gangtaidongman"},
        {"n": "日韩动漫", "v": "rihandongman"},
        {"n": "欧美动漫", "v": "oumeidongman"},
    ],
    "tiyu": [
        {"n": "全部体育", "v": "tiyu"},
    ],
}

# 地区
AREAS = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"},
    {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"},
    {"n": "美国", "v": "美国"},
    {"n": "韩国", "v": "韩国"},
    {"n": "日本", "v": "日本"},
    {"n": "泰国", "v": "泰国"},
    {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"},
    {"n": "德国", "v": "德国"},
    {"n": "印度", "v": "印度"},
    {"n": "其他", "v": "其他"},
]

# 年份
YEARS = [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]
YEARS.insert(0, {"n": "全部", "v": ""})

# 排序
ORDERS = [
    {"n": "时间", "v": ""},
    {"n": "人气", "v": "hits"},
]

# 构建筛选配置
FILTERS = {}
for tid, subs in SUB_CLASSES.items():
    filters = []
    if len(subs) > 1 or (len(subs) == 1 and subs[0]["n"] != "全部体育"):
        filters.append({
            "key": "class",
            "name": "类型",
            "value": [{"n": "全部", "v": ""}] + subs
        })
    if tid in ("dianying", "juji", "dongman", "zongyi"):
        filters.append({"key": "area", "name": "地区", "value": AREAS})
    if tid in ("dianying", "juji", "dongman"):
        filters.append({"key": "year", "name": "年份", "value": YEARS})
    if tid in ("dianying", "juji"):
        filters.append({"key": "order", "name": "排序", "value": ORDERS})
    FILTERS[tid] = filters

# 缓存配置
LIST_CACHE_TTL = 120
DETAIL_CACHE_TTL = 600
HOME_CACHE_TTL = 60
SEARCH_CACHE_TTL = 60
PLAY_CACHE_TTL = 1800

HOME_PAGE_SIZE = 24
LIST_PAGE_SIZE = 48


def _urlencode(s):
    return quote(s or "", safe="")


def _strip(txt):
    return re.sub(r"\s+", " ", txt or "").strip()


def _html_to_text(html):
    """移除HTML标签，返回纯文本"""
    if not html:
        return ""
    txt = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", txt).strip()


class Spider(Spider):
    _RE_PLAYER_JSON = re.compile(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*;?\s*</script>', re.IGNORECASE)
    _RE_PLAYER_JSON2 = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\});', re.DOTALL)
    _RE_VOD_LIST = re.compile(
        r'<li[^>]*>.*?<a[^>]+href="/v/(\d+)\.html"[^>]*>.*?'
        r'data-original="([^"]+)"[^>]*alt="([^"]*)".*?'
        r'class="[^"]*pic-text[^"]*"[^>]*>([^<]*)</div>.*?</li>',
        re.DOTALL
    )
    _RE_VOD_ITEM = re.compile(
        r'<div[^>]+class="stui-vodlist__box"[^>]*>.*?'
        r'<a[^>]+href="/v/(\d+)\.html"[^>]*title="([^"]*)".*?'
        r'data-original="([^"]+)".*?'
        r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([^<]*)</span>.*?'
        r'</div>',
        re.DOTALL
    )
    _RE_DETAIL_INFO = re.compile(
        r'<div[^>]+class="stui-content__detail[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>',
        re.DOTALL
    )
    _RE_PAGE_COUNT = re.compile(r'(\d+)\s*/\s*(\d+)')
    _RE_PLAYLIST = re.compile(
        r'<div[^>]+class="stui-pannel__hd"[^>]*>\s*<h3>\s*.*?播放地址.*?</h3>.*?'
        r'(<div[^>]+class="stui-pannel__bd"[^>]*>[\s\S]*?)\s*<div[^>]+class="stui-pannel"',
        re.DOTALL
    )
    _RE_PLAY_LINE = re.compile(
        r'<ul[^>]+class="stui-content__playlist[^"]*"[^>]*>([\s\S]*?)</ul>',
        re.DOTALL
    )
    _RE_PLAY_ITEM = re.compile(
        r'<li[^>]*><a[^>]+href="(/p/\d+-\d+-\d+\.html)"[^>]*>([^<]+)</a></li>',
        re.DOTALL
    )
    _RE_LINE_NAME = re.compile(
        r'<a[^>]+href="[^"]*#playlist\d+"[^>]*>([^<]+)</a>',
        re.DOTALL
    )

    def getName(self):
        return "VIP电影"

    def init(self, extend=""):
        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        self.ajax_header = dict(self.header)
        self.ajax_header["X-Requested-With"] = "XMLHttpRequest"
        self.ajax_header["Accept"] = "application/json, text/javascript, */*; q=0.01"

        try:
            import requests
            from requests.adapters import HTTPAdapter
            self._session = requests.Session()
            adapter = HTTPAdapter(pool_connections=30, pool_maxsize=30)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
            # 保留默认代理行为，提升兼容性
            # self._session.trust_env = False
        except Exception as e:
            print("[VIP电影] requests 不可用, 回退到框架 fetch: " + str(e))
            self._session = None

        self._list_cache = {}
        self._detail_cache = {}
        self._home_cache = None
        self._search_cache = {}
        self._play_cache = {}
        self._cache_lock = threading.Lock()

    def isVideoFormat(self, url):
        u = (url or "").lower().rstrip("?#")
        return any(u.endswith(ext) for ext in (".m3u8", ".mp4", ".flv", ".ts"))

    def destroy(self):
        sess = getattr(self, "_session", None)
        if sess is not None:
            try:
                sess.close()
            except Exception:
                pass

    def _http_get(self, url, timeout=8, use_ajax=False):
        """HTTP GET请求，带重试"""
        headers = self.ajax_header if use_ajax else self.header
        sess = getattr(self, "_session", None)
        if sess is not None and hasattr(sess, "get"):
            for attempt in range(2):
                try:
                    rsp = sess.get(url, headers=headers, timeout=timeout, verify=False, allow_redirects=True)
                    if getattr(rsp, "status_code", 0) == 200:
                        txt = getattr(rsp, "text", None) or ""
                        if txt:
                            return txt
                except Exception:
                    if attempt == 0:
                        time.sleep(0.3)
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            if getattr(rsp, "status_code", 0) == 200:
                txt = getattr(rsp, "text", None) or ""
                if txt:
                    return txt
        except Exception:
            pass
        return ""

    def _http_get_json(self, url, timeout=6):
        """获取JSON数据"""
        html = self._http_get(url, timeout=timeout, use_ajax=True)
        if not html:
            return None
        try:
            return json.loads(html)
        except Exception:
            return None

    def _build_list_url(self, slug, area="", year="", order="", page=1):
        """构建分类列表URL
        MacCMS URL格式: /s/{slug}-{p1}-{p2}-...-{p11}.html (共12段，11个横杠)
        
        位置说明 (索引从0开始):
          [0]  分类slug
          [1]  地区 (area)
          [2]  排序 (order: time/hits，空表示默认)
          [3-7] 其他参数(语言/版本/状态/字母等)
          [8]  页码 (page，第1页为空)
          [9-10] 其他参数
          [11] 年份 (year)
        
        示例:
          全部电影:          /s/dianying-----------.html
          大陆电影:          /s/dianying-%E5%A4%A7%E9%99%86----------.html
          2024电影:          /s/dianying-----------2024.html
          人气排序:          /s/dianying--hits---------.html
          第2页:             /s/dianying--------2---.html
          大陆2024:          /s/dianying-%E5%A4%A7%E9%99%86----------2024.html
        """
        parts = [""] * 12  # 共12段
        parts[0] = slug
        # 位置1: 地区
        if area:
            parts[1] = _urlencode(area)
        # 位置2: 排序
        if order:
            parts[2] = order
        # 位置8: 页码 (第1页为空)
        if page and page > 1:
            parts[8] = str(page)
        # 位置11: 年份
        if year:
            parts[11] = year
        
        return HOST + "/s/" + "-".join(parts) + ".html"

    def _parse_list_html(self, html):
        """从列表页HTML解析视频列表和分页信息"""
        videos = []
        seen = set()

        # 匹配 stui-vodlist__box 结构
        # 结构: <div class="stui-vodlist__box">
        #         <a href="/v/{id}.html" title="{name}" data-original="{pic}">
        #           <span class="pic-text text-right"><b>{remarks}</b></span>
        #         </a>
        #       </div>
        pattern = (
            r'<div[^>]+class="stui-vodlist__box"[^>]*>'
            r'.*?<a[^>]+href="/v/(\d+)\.html"[^>]*title="([^"]*)"[^>]*'
            r'data-original="([^"]+)"[^>]*>'
            r'.*?'
            r'<span[^>]+class="[^"\s]*pic-text(?:\s[^"]*)?"[^>]*>\s*<b>([^<]*)</b>\s*</span>'
            r'.*?</div>'
        )
        for m in re.finditer(pattern, html, re.DOTALL):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            videos.append({
                "vod_id": vid,
                "vod_name": _strip(m.group(2)),
                "vod_pic": m.group(3),
                "vod_remarks": _strip(m.group(4)),
            })

        # 解析分页
        page = 1
        pagecount = 1
        total = 0

        # 从尾页链接获取总页数
        m = re.search(r'<li><a[^>]+href="/s/[^"]+-+(\d+)---[^"]*\.html"[^>]*>尾页</a>', html)
        if m:
            pagecount = int(m.group(1))
            total = pagecount * LIST_PAGE_SIZE

        # 获取当前页
        m2 = re.search(r'<li[^>]+class="[^"]*active[^"]*"[^>]*><a[^>]*>(\d+)</a></li>', html)
        if m2:
            page = int(m2.group(1))

        # 如果没找到尾页，从分页数字推断
        if pagecount <= 1:
            page_nums = re.findall(
                r'<li[^>]*class="hidden-xs[^"]*"[^>]*><a[^>]+href="/s/[^"]+-+(\d+)---[^"]*\.html"[^>]*>\d+</a></li>',
                html
            )
            if page_nums:
                max_page = max(int(p) for p in page_nums)
                if max_page > pagecount:
                    pagecount = max_page
                    # 这只是可见页，实际总页数可能更多
                    total = pagecount * LIST_PAGE_SIZE

        return videos, page, pagecount, total

    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        now = time.time()
        with self._cache_lock:
            if self._home_cache:
                ts, payload = self._home_cache
                if now - ts < HOME_CACHE_TTL:
                    return payload

        videos = []
        seen = set()
        # 取前3个分类的首页内容
        for tid in ("dianying", "juji", "dongman"):
            url = HOST + "/s/" + tid + "-----------.html"
            html = self._http_get(url, timeout=6)
            if html:
                vlist, _, _, _ = self._parse_list_html(html)
                for v in vlist[:12]:
                    if v["vod_id"] not in seen:
                        seen.add(v["vod_id"])
                        videos.append(v)
                        if len(videos) >= HOME_PAGE_SIZE:
                            break
            if len(videos) >= HOME_PAGE_SIZE:
                break

        payload = {"list": videos[:HOME_PAGE_SIZE]}
        with self._cache_lock:
            self._home_cache = (now, payload)
        return payload

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            ext = extend or {}
            cls = str(ext.get("class", "") or "")
            area = str(ext.get("area", "") or "")
            year = str(ext.get("year", "") or "")
            order = str(ext.get("order", "") or "")

            # 如果选了二级分类，用二级分类的slug
            use_slug = cls if cls else str(tid)

            cache_key = (use_slug, area, year, order, page)
            now = time.time()
            with self._cache_lock:
                hit = self._list_cache.get(cache_key)
                if hit and now - hit[0] < LIST_CACHE_TTL:
                    return hit[1]

            url = self._build_list_url(use_slug, area=area, year=year, order=order, page=page)
            html = self._http_get(url, timeout=8)

            if not html:
                return {"list": [], "page": page, "pagecount": 1, "limit": LIST_PAGE_SIZE, "total": 0}

            videos, cur_page, pagecount, total = self._parse_list_html(html)

            payload = {
                "list": videos,
                "page": cur_page or page,
                "pagecount": pagecount or 1,
                "limit": len(videos) or LIST_PAGE_SIZE,
                "total": total,
            }
            with self._cache_lock:
                self._list_cache[cache_key] = (now, payload)
            return payload
        except Exception as e:
            print("[VIP电影] categoryContent 异常: " + str(e))
            return {"list": [], "page": 1, "pagecount": 1, "limit": LIST_PAGE_SIZE, "total": 0}

    def _parse_detail_html(self, html, vod_id):
        """从详情页HTML解析视频详情和播放列表"""
        vod = {
            "vod_id": str(vod_id),
            "vod_name": "",
            "vod_pic": "",
            "vod_year": "",
            "vod_area": "",
            "vod_lang": "",
            "vod_remarks": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_class": "",
            "vod_content": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }

        # 提取标题 (优先从h1.title)
        m = re.search(r'<h1[^>]+class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>', html)
        if m:
            vod["vod_name"] = _strip(m.group(1))

        # 从title标签提取备用标题
        if not vod["vod_name"]:
            m2 = re.search(r'<title>([^<|]+)</title>', html)
            if m2:
                vod["vod_name"] = _strip(m2.group(1))

        # 提取详情区域
        detail_match = re.search(
            r'<div[^>]+class="stui-content__detail[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>',
            html, re.DOTALL
        )
        if not detail_match:
            # 备用：找包含详情信息的区域
            detail_match = re.search(
                r'<div[^>]+class="[^"]*content__detail[^"]*"[^>]*>([\s\S]{100,}?)</div>',
                html, re.DOTALL
            )

        if detail_match:
            detail_html = detail_match.group(1)

            # 提取图片 (从thumb区域)
            pic_match = re.search(
                r'<img[^>]+(?:data-original|src)="([^"]+)"[^>]*>',
                detail_html, re.DOTALL
            )
            if pic_match and pic_match.group(1).startswith("http"):
                vod["vod_pic"] = pic_match.group(1)

            # 提取所有 text-muted / subtitle 行的信息
            # 模式1: <p class="text text-muted">标签：值</p>
            info_patterns = [
                (r'类型[：:]\s*([^<\n/]+)', "vod_class"),
                (r'地区[：:]\s*([^<\n/]+)', "vod_area"),
                (r'年份[：:]\s*([^<\n/]+)', "vod_year"),
                (r'语言[：:]\s*([^<\n/]+)', "vod_lang"),
                (r'状态[：:]\s*([^<\n/]+)', "vod_remarks"),
                (r'导演[：:]\s*([^<\n/]+)', "vod_director"),
                (r'主演[：:]\s*([^<\n/]+)', "vod_actor"),
                (r'演员[：:]\s*([^<\n/]+)', "vod_actor"),
            ]

            for pattern, key in info_patterns:
                m = re.search(pattern, detail_html)
                if m and not vod.get(key):
                    val = _strip(m.group(1))
                    if val:
                        vod[key] = val

            # 如果有"类型：xx / 地区：xx / 年份：xx"格式的行
            combined_match = re.search(
                r'类型[：:]\s*([^<\n/]+?)\s*/\s*地区[：:]\s*([^<\n/]+?)\s*/\s*年份[：:]\s*([^<\n]+)',
                detail_html
            )
            if combined_match:
                if not vod["vod_class"]:
                    vod["vod_class"] = _strip(combined_match.group(1))
                if not vod["vod_area"]:
                    vod["vod_area"] = _strip(combined_match.group(2))
                if not vod["vod_year"]:
                    vod["vod_year"] = _strip(combined_match.group(3))

        # 从页面其他位置提取图片
        if not vod["vod_pic"]:
            pic_match = re.search(
                r'<div[^>]+class="stui-content__thumb[^"]*"[^>]*>.*?'
                r'<img[^>]+(?:data-original|src)="([^"]+)"',
                html, re.DOTALL
            )
            if pic_match:
                vod["vod_pic"] = pic_match.group(1)

        # 提取简介
        # 模式1: detail-desc
        intro_match = re.search(
            r'<div[^>]+class="[^"]*detail-desc[^"]*"[^>]*>([\s\S]*?)</div>',
            html, re.DOTALL
        )
        if intro_match:
            intro_text = _html_to_text(intro_match.group(1))
            # 去掉"简介："前缀
            intro_text = re.sub(r'^简介[：:]\s*', '', intro_text)
            vod["vod_content"] = intro_text[:500]

        # 模式2: content__content
        if not vod["vod_content"]:
            intro_match2 = re.search(
                r'<span[^>]+class="content__content"[^>]*>([\s\S]*?)</span>',
                html, re.DOTALL
            )
            if intro_match2:
                vod["vod_content"] = _html_to_text(intro_match2.group(1))[:500]

        # 模式3: 从介绍行提取
        if not vod["vod_content"]:
            intro_match3 = re.search(r'介绍[：:]\s*([\s\S]{20,}?)(?:<br|</p>|更新[：:])', html)
            if intro_match3:
                vod["vod_content"] = _html_to_text(intro_match3.group(1))[:500]

        # 提取播放列表
        play_from, play_url = self._extract_playlists(html, vod_id)
        if play_from:
            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_url)

        return vod

    def _extract_playlists(self, html, vod_id):
        """从详情页提取播放线路和集数
        返回 (play_from列表, play_url列表)
        """
        play_from = []
        play_url = []

        # 提取播放线路名称 (playlist标签)
        # 格式: <a href="#playlist1">线路名</a>
        line_names = []
        for m in re.finditer(
            r'<a[^>]+href="#playlist(\d+)"[^>]*>([^<]+)</a>',
            html
        ):
            sid = int(m.group(1))
            name = _strip(m.group(2))
            if name:
                line_names.append((sid, name))

        # 查找所有播放列表区域
        # 播放地址板块的结构:
        # <div class="stui-pannel">
        #   <div class="stui-pannel__hd"><h3>播放地址</h3></div>
        #   <div class="stui-pannel__bd">
        #     <ul class="stui-content__playlist">...线路1的集数...</ul>
        #     <ul class="stui-content__playlist">...线路2的集数...</ul>
        #   </div>
        # </div>

        # 先找到播放地址板块
        play_section = None
        # 模式1: 从"播放地址"标题后找ul列表
        for m in re.finditer(
            r'(播放地址|在线播放|播放源)[\s\S]{0,200}?</div>\s*<div[^>]+class="stui-pannel__bd"[^>]*>([\s\S]*?)</div>\s*</div>',
            html, re.DOTALL
        ):
            play_section = m.group(2)
            break

        # 模式2: 直接找所有stui-content__playlist
        all_uls = re.findall(
            r'<ul[^>]+class="stui-content__playlist[^"]*"[^>]*>([\s\S]*?)</ul>',
            html if not play_section else play_section,
            re.DOTALL
        )

        # 过滤出包含有效播放链接的ul
        valid_uls = []
        for ul_html in all_uls:
            items = re.findall(
                r'<li[^>]*>\s*<a[^>]+href="(/p/\d+-\d+-\d+\.html)"[^>]*>([^<]+)</a>\s*</li>',
                ul_html, re.DOTALL
            )
            if items:
                valid_uls.append(items)

        if valid_uls:
            for idx, items in enumerate(valid_uls):
                sid = idx + 1
                # 尝试匹配线路名
                line_name = "线路" + str(sid)
                for ln_sid, ln_name in line_names:
                    if ln_sid == sid:
                        line_name = ln_name
                        break

                eps_str = []
                for href, name in items:
                    ep_name = _strip(name)
                    if ep_name:
                        eps_str.append(ep_name + "$" + href)

                if eps_str:
                    play_from.append(line_name)
                    play_url.append("#".join(eps_str))

        # 如果没找到分组的ul，尝试从所有播放链接按sid分组
        if not play_from:
            sid_groups = {}
            for m in re.finditer(
                r'href="(/p/(\d+)-(\d+)-(\d+)\.html)"[^>]*>([^<]+)</a>',
                html
            ):
                path, vid, sid, nid, name = m.groups()
                sid = int(sid)
                if sid not in sid_groups:
                    sid_groups[sid] = []
                ep_name = _strip(name)
                if ep_name:
                    sid_groups[sid].append((int(nid), ep_name, path))

            if sid_groups:
                for sid in sorted(sid_groups.keys()):
                    eps = sorted(sid_groups[sid], key=lambda x: x[0])
                    eps_str = [name + "$" + path for _, name, path in eps]
                    if eps_str:
                        line_name = "线路" + str(sid)
                        for ln_sid, ln_name in line_names:
                            if ln_sid == sid:
                                line_name = ln_name
                                break
                        play_from.append(line_name)
                        play_url.append("#".join(eps_str))

        return play_from, play_url

    def detailContent(self, ids):
        try:
            if isinstance(ids, (list, tuple)):
                ids = ids[0]
            vod_id = str(ids)
            now = time.time()
            with self._cache_lock:
                hit = self._detail_cache.get(vod_id)
                if hit and now - hit[0] < DETAIL_CACHE_TTL:
                    return hit[1]

            detail_url = HOST + "/v/" + vod_id + ".html"
            html = self._http_get(detail_url, timeout=8)

            if not html:
                return {"list": []}

            vod = self._parse_detail_html(html, vod_id)

            # 如果没找到图片，再尝试从其他位置找
            if not vod.get("vod_pic"):
                m = re.search(
                    r'<div[^>]+class="stui-content__thumb[^"]*"[^>]*>.*?'
                    r'<img[^>]+(?:data-original|src)="([^"]+)"',
                    html, re.DOTALL
                )
                if m:
                    vod["vod_pic"] = m.group(1)

            payload = {"list": [vod]}
            with self._cache_lock:
                self._detail_cache[vod_id] = (now, payload)
            return payload
        except Exception as e:
            print("[VIP电影] detailContent 异常: " + str(e))
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            cache_key = (key, page)
            now = time.time()
            with self._cache_lock:
                hit = self._search_cache.get(cache_key)
                if hit and now - hit[0] < SEARCH_CACHE_TTL:
                    return hit[1]

            # 优先使用JSON搜索接口
            kw = _urlencode(key)
            json_url = HOST + "/index.php/ajax/suggest?mid=1&wd=" + kw + "&limit=20&page=" + str(page)
            data = self._http_get_json(json_url, timeout=5)

            videos = []
            total = 0
            pagecount = 1

            if data and data.get("code") == 1:
                for item in data.get("list", []):
                    vid = str(item.get("id", ""))
                    if not vid:
                        continue
                    videos.append({
                        "vod_id": vid,
                        "vod_name": _strip(item.get("name", "")),
                        "vod_pic": item.get("pic", ""),
                        "vod_remarks": "",
                    })
                total = data.get("total", 0) or 0
                pagecount = data.get("pagecount", 1) or 1

            # 如果JSON接口没结果，回退到HTML搜索页
            if not videos:
                # 搜索页URL格式: /sou/{keyword}-------------.html (13个横杠)
                search_url = HOST + "/sou/" + kw + "-------------.html"
                html = self._http_get(search_url, timeout=8)
                if html:
                    vlist, _, pc, tot = self._parse_list_html(html)
                    videos = vlist
                    pagecount = pc
                    total = tot

            payload = {
                "list": videos,
                "page": page,
                "pagecount": pagecount or 1,
                "limit": len(videos) or 20,
                "total": total,
            }
            with self._cache_lock:
                self._search_cache[cache_key] = (now, payload)
            return payload
        except Exception as e:
            print("[VIP电影] searchContent 异常: " + str(e))
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _parse_player_page(self, html):
        """从播放页HTML解析真实播放地址"""
        # 尝试匹配 player_aaaa
        m = self._RE_PLAYER_JSON.search(html)
        if not m:
            m = self._RE_PLAYER_JSON2.search(html)

        if m:
            try:
                player = json.loads(m.group(1))
                return player
            except Exception:
                pass

        # 备用模式：找 var player_aaaa = { ... };
        m2 = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\n\})', html)
        if m2:
            try:
                player = json.loads(m2.group(1))
                return player
            except Exception:
                pass

        return None

    def playerContent(self, flag, id, vipFlags):
        play_path = str(id or "")
        if not play_path:
            return {"parse": 0, "url": ""}

        # 如果已经是直链
        if self.isVideoFormat(play_path):
            return {"parse": 0, "url": play_path, "header": {"User-Agent": UA, "Referer": HOST + "/"}}

        # 检查播放缓存
        now = time.time()
        cache_key = play_path
        with self._cache_lock:
            hit = self._play_cache.get(cache_key)
            if hit and now - hit[0] < PLAY_CACHE_TTL:
                cached_url, cached_from = hit[1]
                if cached_url and self.isVideoFormat(cached_url):
                    return {
                        "parse": 0,
                        "url": cached_url,
                        "header": {"User-Agent": UA, "Referer": HOST + "/"}
                    }

        if "/p/" in play_path:
            if play_path.startswith("http"):
                play_url = play_path
            else:
                play_url = HOST + play_path

            html = self._http_get(play_url, timeout=8)
            if not html:
                return {"parse": 1, "url": play_url, "header": {"User-Agent": UA, "Referer": HOST + "/"}}

            player = self._parse_player_page(html)
            if player:
                real_url = player.get("url", "")
                from_name = player.get("from", "")

                # 缓存播放地址
                if real_url:
                    with self._cache_lock:
                        self._play_cache[cache_key] = (now, (real_url, from_name))

                if real_url and real_url.startswith("http"):
                    if self.isVideoFormat(real_url):
                        return {
                            "parse": 0,
                            "url": real_url,
                            "header": {
                                "User-Agent": UA,
                                "Referer": HOST + "/",
                            },
                        }
                    else:
                        # 可能是需要解析的链接
                        return {
                            "parse": 1,
                            "url": real_url,
                            "header": {
                                "User-Agent": UA,
                                "Referer": HOST + "/",
                            }
                        }

            # 没解析到，返回播放页让TVBox自己解析
            return {
                "parse": 1,
                "url": play_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": HOST + "/",
                }
            }

        return {"parse": 0, "url": play_path, "header": {"User-Agent": UA, "Referer": HOST + "/"}}

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]
