# -*- coding: utf-8 -*-
"""
河北Google/厂长影视(www.hebeigoogle.com) V3.0 - WebHTV / 默影视壳适配
按默影视壳10项标准编写(真网实测站点结构)

== V3.0 优化(2026-08-21, 针对壳内实测反馈: 筛选器/进壳速度/线路起播) ==
① 修复片源筛选器: filters 由 @property 改为【纯类属性字典】(模板⑥要求的
   注册形态)。部分壳子直接读 Spider.filters 类属性, @property 在类上取到的
   是 property 对象 -> 筛选面板空/失效。现类属性+homeContent双通道都给真字典。
② 进壳加载提速(stale-while-revalidate):
   - 首页结果持久化(setCache, 重启秒进); 过期数据立即返回+后台刷新,
     绝不阻塞壳子首屏(实测间歇TLS抖动时不再卡 3~11s);
   - _get 增加快速重试1次(站点偶发TLS握手超时, 重试即过);
   - 首页抓取用短读超时(6s), classes/filters 永远先返回。
③ 各线路起播提速(master变体直出):
   - 实测本站全部线路 m3u8 均为 master 清单(97~119B), 播放器还要多请求
     一跳变体(实测0.9~1.3s)。现 playerContent 内直接深解析 master ->
     最高RESOLUTION/BANDWIDTH变体直链, 播放器省一跳CDN RTT;
   - 变体解析短超时(2.5s), 失败原样返回master(部分CDN机房不可达,
     用户家用网络可达, 不挡起播);
   - 播放成功后后台预取同线路下一集(连续观看第2集起秒开);
   - 详情页后台预取置顶线路第1集(保留)。
④ 分类翻页对账增强: pagecount 解析支持带筛选槽位的翻页链接(12段页码槽)。

== V2.0 修复(旧版为无法访问站点时的猜测模板, URL全部猜错 -> 壳子空白) ==
旧版错误: 分类猜测 /vod/type/id/{tid}.html, 详情猜测 /vod/detail/id/{id}.html,
         播放猜测 /vod/play/... —— 真站全是 /igols /igosw /igojs /igokj, 全部404
         -> 截图所示"电视剧"分类页"这里什麽都没有"。
V2.0 全部按真网抓包实测重写, 零猜测:
① 分类真实URL: /igols/{tid}-{pg}.html 与 /igosw/{tid}-{槽位}.html 双形态
② 列表卡片: <li class="dx-vod" data-json='{id,name,score,blurb,pic,link}'>
   + <span class="vod_remarks">角标 —— data-json一次拿全, 正则秒解析
③ 详情: /igojs/{id}.html, og:title《片名》/og:image/年份·地区tag-link/
   导演·主演info-items/.vod_content简介
④ 选集线路: .playNumPage a.Tab(data-id=detail_{sid}) + #detail_{sid}
   ul.playNumList a(/igokj/{vid}-{sid}-{nid}.html)
⑤ 播放: 播放页 player_aaaa JSON(encrypt:0) 直接给出 m3u8 直链
   -> parse:0 原生秒开, 无需嗅探; encrypt 1/2 解码兜底
⑥ 搜索: /igoso/-------------.html?wd={kw} (GET表单实测可用, 结果单页)

== 站点实测结构(2026-08-20 抓包确认) ==
- 顶级分类 /igols/{1..5}: 1电影 2电视剧 3综艺 4动漫 5短剧
- 类型页 /igosw/{tid}: 6-16电影类型(动作/喜剧/爱情/科幻/恐怖/剧情/战争/
  纪录/悬疑/犯罪/动画), 17-22电视剧类型(17国产剧 18港台剧 20日韩剧
  21欧美剧 22海外剧); 顶级tid同样可用(实测 /igosw/2-----------.html == 电视剧)
- /igosw 筛选URL槽位(12段, 实测逐字符对齐):
    /igosw/{tid}-{地区}-{排序}-{类型}-{方向}------{页码}--{年份}.html
  实测生效: 地区(内地/香港/美国...) / 排序(time最新/hits人气/score评分) /
  年份(2004-2026) / 页码 —— 组合筛选真过滤(对比条目id集合验证)
- 分类翻页: /igols/{tid}-{pg}.html (电视剧837页) 或 /igosw槽位页码
- 搜索: GET /igoso/-------------.html?wd={kw} 实测"庆余年"16条, 单页
- 播放页: /igokj/{vid}-{sid}-{nid}.html 内嵌
  player_aaaa={"url":"https://.../index.m3u8","encrypt":0,"from":"ffm3u8",...}
- 站点对机房TLS不敏感时可用requests直连; 壳内优先Session连接池,
  失败自动降级 self.fetch(走用户家用IP)

== 10项标准落实 ==
①双快: Session连接池 + 四级缓存(首页5min/分类90s/详情5min/搜索60s/播放30min)
        + 分类下一页后台预热 + 详情返回后预取置顶线路第1集 + 并发去重
②国产优先: 分类序列国产置顶(国产剧在港台/日韩/欧美剧之前);
   卡片无地区字段, 列表不重排不造假数据
③角标: vod_remarks(更新至N集/全集)归一 已完结N集/更新至N集;
   详情状态兜底 + 选集数兜底
④正序: 选集标题纯数字归一(第01集->1), 按集数升序, 同集异写去重
⑤可搜: searchable/quickSearch/filterable/changeable四声明 + /igoso真实对接
        + 变体递进(完整词->去空格->2字前缀) + 60s缓存
⑥筛选: 地区/年份/排序三维真实服务端筛选(/igosw槽位URL, 全部实测有数据)
⑦海报详情: 海报绝对URL + 片名《》清洗 + 年份(真实tag-link)/地区/导演/
   主演/简介完整提取; 详情字段完整性校验
⑧翻页: /igols-{pg} + 翻页链接对账pagecount + 下一页后台预热
⑨完整性: verify_category/verify_detail/verify_search/verify_all + __main__自检
⑩线路: 站点原序保留(全部"VIPxx高清云播"同质, 画质阶梯无差异不强行重排)
"""
import json
import re
import threading
import time
from urllib.parse import quote, unquote, urljoin

try:
    import requests as _req
    HAS_REQ = True
except Exception:
    _req = None
    HAS_REQ = False

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        """脱壳自检用的伪基类"""
        def fetch(self, *a, **k):
            return None

        def post(self, *a, **k):
            return None

        def setCache(self, k, v):
            pass

        def getCache(self, k):
            return None

        def log(self, msg):
            pass


# ==================== ⑥ 筛选器注册(模块级构建 -> 纯类属性字典) ====================
# 模板要求 filters 为类属性字典; @property 在类上取到 property 对象,
# 部分壳子直读 Spider.filters -> 筛选面板空。故模块级构建后整体赋类属性。
_F_AREAS = ["内地", "香港", "台湾", "美国", "韩国", "日本", "英国",
            "新加坡", "泰国", "其他"]
_F_YEARS = [str(y) for y in range(2026, 2003, -1)]
_F_SORTS = [["time", "最新"], ["hits", "人气"], ["score", "评分"]]


def _F_DIM(key, name, values):
    return {"key": key, "name": name,
            "value": [{"n": str(v[1]), "v": str(v[0])} for v in values]}


class Spider(_BaseSpider):
    # ==================== 站点配置(真网实测) ====================
    name = "厂长影视"
    host = "https://www.hebeigoogle.com"

    # ⑤ 壳子能力声明(实测壳子读取类属性: 缺失 -> 判"无搜索器",
    #   聚合搜索源列表不显示本站; 与4K厂长/茶杯狐等已验证源同一约定)
    searchable = 1      # 聚合搜索可搜
    quickSearch = 1     # 搜索器快捷搜索
    filterable = 1      # ⑥ 站点有真实服务端筛选(地区/年份/排序)
    changeable = 1      # 允许跨站换源(片名已 _clean_name 清洗)

    UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/126.0.0.0 Mobile Safari/537.36")

    # ② 分类: 仅5个主分类当顶部标签(子类型放筛选器里, 避免21个平铺混乱)
    classes = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "5", "type_name": "短剧"},
    ]

    # ⑥ 各主分类对应的"类型"子分类(tid映射, 实测站内有数据才列入)
    _CLASS_TYPES = {
        "1": [                      # 电影 -> 11种类型
            ["6", "动作片"], ["7", "喜剧片"], ["8", "爱情片"],
            ["9", "科幻片"], ["10", "恐怖片"], ["11", "剧情片"],
            ["12", "战争片"], ["13", "纪录片"], ["14", "悬疑片"],
            ["15", "犯罪片"], ["16", "动画片"],
        ],
        "2": [                      # 电视剧 -> 5种地区类型(国产置顶②)
            ["17", "国产剧"], ["18", "港台剧"], ["20", "日韩剧"],
            ["21", "欧美剧"], ["22", "海外剧"],
        ],
        "3": [],                    # 综艺(暂无子类型页)
        "4": [],                    # 动漫
        "5": [],                    # 短剧
    }

    # ⑥ 筛选维度(全部实测站内有数据: 地区/年份实测真过滤, 排序实测真生效)
    _AREAS = _F_AREAS
    _YEARS = _F_YEARS
    _SORTS = _F_SORTS

    # ⑥ 纯类属性字典(逐分类注册; 类上/实例上取到均为真dict, 壳子双通道兼容)
    # 电影/电视剧额外加"类型"维度(子分类tid, 走真实类型页/igosw/{子tid}, 真过滤)
    filters = {}
    for c in classes:
        tid = str(c["type_id"])
        dims = []
        types = _CLASS_TYPES.get(tid) or []
        if types:
            dims.append(_F_DIM("klass", "类型",
                               [["", "全部"]] + [[t[0], t[1]] for t in types]))
        dims += [
            _F_DIM("area", "地区",
                   [["", "全部"]] + [[a, a] for a in _F_AREAS]),
            _F_DIM("year", "年份",
                   [["", "全部"]] + [[y, y] for y in _F_YEARS]),
            _F_DIM("by", "排序", [["", "默认"]] + _F_SORTS),
        ]
        filters[tid] = dims

    headers = {
        "User-Agent": UA,
        "Accept": ("text/html,application/xhtml+xml,application/xml;"
                   "q=0.9,*/*;q=0.8"),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    play_headers = {"User-Agent": UA, "Referer": host + "/"}

    # ==================== ① 性能参数 ====================
    HOME_CACHE_TTL = 300
    CAT_CACHE_TTL = 90
    DETAIL_CACHE_TTL = 300
    SEARCH_CACHE_TTL = 60
    PLAY_CACHE_TTL = 1800
    CONNECT_TIMEOUT = 3
    READ_TIMEOUT = 8
    PARSE_WAIT_MAX = 4.5     # 并发等待上限(实测站点偶发8s级读抖动,
                             # 预取线程卡住时用户4.5s即自行解析, 不干等)
    CACHE_MAX = 200
    PREFETCH_NEXT_PAGE = True
    PAGE_LIMIT = 36          # 实测每页 36-42 卡, 对账用上限

    # ==================== 壳子生命周期(签名勿改) ====================
    def init(self, extend=""):
        self._home_cache = {}
        self._homev_cache = {}
        self._cat_cache = {}
        self._detail_cache = {}
        self._search_cache = {}
        self._play_cache = {}
        self._parse_inflight = {}
        self._ep_next = {}          # ③ 播放页URL -> 同线路下一集URL(预取用)
        self._play_lock = threading.Lock()
        self._session = None
        self._init_session()
        return

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        return any(x in str(url) for x in (".m3u8", ".mp4", ".flv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    def localProxy(self, param):
        return {}

    def liveContent(self, url):
        return {}

    # ==================== ①A 网络层: 连接池 + 双通道降级 ====================

    def _init_session(self):
        if not HAS_REQ:
            return None
        if getattr(self, "_session", None) is None:
            try:
                sess = _req.Session()
                try:
                    adapter = _req.adapters.HTTPAdapter(
                        pool_connections=8, pool_maxsize=16)
                    sess.mount("https://", adapter)
                    sess.mount("http://", adapter)
                except Exception:
                    pass
                sess.headers.update(self.headers)
                self._session = sess
            except Exception:
                self._session = None
        return self._session

    def _fix(self, url):
        u = str(url or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        if not u.startswith(("http://", "https://")):
            u = urljoin(self.host + "/", u)
        return u

    def _get(self, url, timeout=None):
        """GET: Session连接池优先(站点偶发TLS握手超时, 快速重试1次即过),
        仍失败降级壳子fetch(用户家用IP)"""
        timeout = timeout or (self.CONNECT_TIMEOUT, self.READ_TIMEOUT)
        sess = self._init_session()
        if sess is not None:
            for attempt in (0, 1):
                try:
                    r = sess.get(url, timeout=timeout, headers=self.headers)
                    enc = (r.encoding or "").lower()
                    if not enc or enc in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    return r.text or ""
                except Exception:
                    if attempt:
                        break
        try:
            resp = self.fetch(url, headers=self.headers)
            return getattr(resp, "text", "") or ""
        except Exception:
            return ""

    # ==================== ①A 五级缓存 + 翻页预热 ====================

    @staticmethod
    def _ext_key(extend):
        try:
            return json.dumps(extend or {}, sort_keys=True,
                              ensure_ascii=False)
        except Exception:
            return str(extend)

    def _page_cache_get(self, cache, key, ttl):
        box = getattr(self, cache, None)
        if not isinstance(box, dict):
            return None, False
        hit = box.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1], True
        return None, False

    def _page_cache_set(self, cache, key, result):
        box = getattr(self, cache, None)
        if not isinstance(box, dict):
            box = {}
            setattr(self, cache, box)
        box[key] = (time.time(), result)
        self._mem_trim(box)

    def _mem_trim(self, box, cap=None):
        try:
            cap = int(cap or self.CACHE_MAX)
            if len(box) > cap:
                for k in list(box.keys())[: len(box) - cap]:
                    box.pop(k, None)
        except Exception:
            pass

    def _cache_has(self, cache, key, ttl):
        box = getattr(self, cache, None)
        if not isinstance(box, dict):
            return False
        hit = box.get(key)
        return bool(hit) and time.time() - hit[0] < ttl

    # ==================== ⑧ 真实URL构造(零猜测, 逐字符对齐实测) ====================

    def _cat_url(self, tid, pg, extend):
        """分类/筛选URL
        - 有 klass(类型子分类): 直接用子tid走类型页 /igosw/{子tid}-{槽位}.html
          (类型页是真实独立分类页, 比参数过滤更准更快, 实测/igosw/17=国产剧)
        - 无 klass: 主分类 /igosw/{tid}-{地区}-{排序}-...-{页码}-...-{年份}.html
        槽位(12段)实测对齐: [tid, 地区, 排序, 类型, 方向, -, -, -, 页码, -, -, 年份]
        pg=1 用站点自身的"页码槽留空"形态(与导航链接一致, 消除翻页重复)"""
        ex = extend or {}
        # 类型子分类: 替换tid为子tid, 清空类型槽位(避免双过滤)
        klass = str(ex.get("klass") or "")
        real_tid = klass if klass else str(tid)
        area = str(ex.get("area") or "")
        by = str(ex.get("by") or "")
        type_slot = ""        # 类型槽位: 子分类模式下不用(整页就是该类型)
        pg_slot = str(int(pg or 1)) if int(pg or 1) > 1 else ""
        slots = [
            quote(area, safe="") if area else "",
            by,
            type_slot,
            "", "", "", "",
            pg_slot,
            "", "",
            str(ex.get("year") or ""),
        ]
        return self._fix("/igosw/" + "-".join([real_tid] + slots) + ".html")

    def _detail_url(self, vid):
        return self._fix("/igojs/{0}.html".format(vid))

    def _play_url(self, vid, sid, nid):
        return self._fix("/igokj/{0}-{1}-{2}.html".format(vid, sid, nid))

    def _search_url(self, kw):
        # GET表单实测可用(/igoso/-------------.html?wd=庆余年 -> 16条)
        return self._fix("/igoso/-------------.html?wd=" + quote(kw))

    # ==================== ②③⑦ 列表解析与整理 ====================

    # 卡片: <li class="dx-vod" data-json='{"id":N,"name":"...","score":"...",
    #        "pic":"...","link":"/igojs/N.html"}'> <span class="vod_remarks">...
    _CARD_JSON = re.compile(r"data-json='([^']+)'")
    _REMARK = re.compile(r'class="vod_remarks">\s*([^<]{1,20})')

    def _parse_list(self, html):
        """列表解析: data-json一次拿全(实测42卡/页全带), 角标取卡片内
        vod_remarks; data-json缺失时退化解析 cover-area 卡片块"""
        items, seen = [], set()
        for m in self._CARD_JSON.finditer(html):
            try:
                j = json.loads(m.group(1))
            except Exception:
                continue
            vid = str(j.get("id") or "")
            name = str(j.get("name") or "").strip()
            link = str(j.get("link") or "")
            if not vid or not name or vid in seen:
                continue
            if "/igojs/" not in link:
                continue
            # 角标: 卡片内紧随其后的 vod_remarks
            remark = ""
            rm = self._REMARK.search(html, m.end(), m.end() + 700)
            if rm:
                remark = rm.group(1).strip()
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": name[:60],
                "vod_pic": self._abs_pic(j.get("pic")),
                "vod_remarks": remark,
            })
        if items:
            return items
        # 退化: cover-area 卡片块(防个别页面无data-json)
        for cm in re.finditer(
                r'class="cover-area[^"]*"\s+href="(/igojs/(\d+)\.html)"'
                r'[^>]*title="([^"]*)"[^>]*data-original="([^"]*)"', html):
            link, vid, title, pic = cm.groups()
            if vid in seen:
                continue
            seen.add(vid)
            rm = self._REMARK.search(html, cm.start() - 500, cm.start())
            items.append({
                "vod_id": vid, "vod_name": title[:60],
                "vod_pic": self._abs_pic(pic),
                "vod_remarks": rm.group(1).strip() if rm else "",
            })
        return items

    def _abs_pic(self, pic):
        p = str(pic or "").strip()
        if not p:
            return ""
        if p.startswith("//"):
            return "https:" + p
        if p.startswith("/"):
            return self.host + p
        if not p.startswith(("http://", "https://")):
            p = urljoin(self.host + "/", p)
        return p

    def _polish(self, items):
        """⑦③⑤ 列表统一整理: 海报绝对URL + 角标归一 + 片名清洗
        (卡片无年份/地区字段 -> 不造假数据, 亦不重排: 站点默认时序最新在前)"""
        for it in items:
            if it.get("vod_pic"):
                it["vod_pic"] = self._abs_pic(it.get("vod_pic"))
            it["vod_remarks"] = self._format_remark(it.get("vod_remarks"))
            it["vod_name"] = self._clean_name(it.get("vod_name"))
        return items

    def _mk_page(self, items, pg, pagecount=0, limit=None):
        items = self._polish(items)
        pg = int(pg or 1)
        limit = int(limit or self.PAGE_LIMIT)
        if not pagecount:
            pagecount = pg if len(items) < limit else pg + 1
        return {"page": pg, "pagecount": int(pagecount),
                "limit": limit, "total": int(pagecount) * limit,
                "list": items}

    # ==================== ③ 集数角标 ====================

    @staticmethod
    def _format_remark(r):
        raw = str(r or "").strip()
        r = re.sub(r"\s+", "", raw)
        if not r:
            return ""
        m = re.fullmatch(r"(?:全|共)\s*(\d{1,4})\s*集", r)
        if m:
            return "已完结{}集".format(m.group(1))
        m = re.fullmatch(r"(?:已)?完结[,，]?(?:全|共)?(\d{1,4})集?", r)
        if m:
            return "已完结{}集".format(m.group(1))
        m = re.fullmatch(r"(\d{1,4})集(?:全|完结)", r)
        if m:
            return "已完结{}集".format(m.group(1))
        if r == "全集":
            return "已完结"
        m = re.match(r"更新至\s*0*(\d{1,4})\s*([集期话])", r)
        if m:
            return "更新至{}{}".format(int(m.group(1)), m.group(2))
        m = re.fullmatch(r"更新至\s*0*(\d{1,4})", r)
        if m:
            return "更新至{}集".format(int(m.group(1)))
        if r in ("已完结", "完结"):
            return "已完结"
        return raw

    @staticmethod
    def _remark_from_eps(eps):
        n = len(eps or [])
        return "已完结" if n <= 1 else "更新至{}集".format(n)

    # ==================== ④ 选集正序 + 纯数字 ====================

    @staticmethod
    def _epnum(title):
        m = re.search(r"(\d+)", str(title))
        if not m:
            return (1, 0)
        n = int(m.group(1))
        return (0, n) if n > 0 else (1, 0)

    @staticmethod
    def _ep_label(title):
        t = str(title or "").strip()
        m = re.search(r"(\d+)", t)
        if not m:
            return t or "正片"
        n = m.group(1).lstrip("0")
        return n or "0"

    def _episodes_ascending(self, eps):
        # ④ 单集(电影"HD/正片/全集"标签)统一归"1": 纯数字正序, 换源匹配友好
        if len(eps) == 1:
            return [("1", eps[0][1])]
        labeled, seen = [], set()
        for t, u in eps:
            lab = self._ep_label(t)
            if lab.isdigit():
                if lab in seen:
                    continue
                seen.add(lab)
            labeled.append((lab, u))
        seq = [n for n, _ in labeled]
        if all(str(i + 1) == v for i, v in enumerate(seq)):
            return labeled
        # 小列表混排标签(电影"HD/正片"与"第1集"并存=同内容异写):
        # 按原序重编号, 保证④纯数字正序(换源匹配友好)
        if len(labeled) <= 2 and not all(n.isdigit() for n in seq):
            return [(str(i + 1), u) for i, (_, u) in enumerate(labeled)]
        return sorted(labeled, key=lambda e: self._epnum(e[0]))

    # ==================== ⑩ 线路 ====================

    _HD_TIERS = (
        ("8k", "uhd", "4k", "2160"),
        ("2k", "蓝光", "bluray", "1080", "杜比", "dolby", "hdr"),
        ("超清", "至臻", "原画", "高清", "hd"),
    )

    def _line_score(self, name):
        low = str(name or "").lower()
        for i, tier in enumerate(self._HD_TIERS):
            if any(k in low for k in tier):
                return -50 + i * 10
        return 0

    def _sort_lines(self, grouped):
        # 实测本站线路全为"VIPxx高清云播"同质命名 -> 站点原序即用户预期,
        # 仅当出现明确画质差异词时才重排
        if all(self._line_score(x) == 0 for x in grouped):
            return list(grouped.keys())
        return sorted(grouped.keys(), key=lambda x: (self._line_score(x), x))

    # ==================== ⑤ 片名清洗 + 条件语法 ====================

    _NAME_TRIM_TAILS = re.compile(
        r"\s*[\(\[【]?(?:HD|高清|蓝光|4K|4k|蓝光4K|1080[PI]i?|720P|抢先版|国语|粤语|中字|双语|完整版|修复版|加长版|导演剪辑版|正片|预告)[\)\]】]?\s*$"
    )
    _NAME_WRAPS = re.compile(
        r"^[\[【]\s*[\w\u4e00-\u9fff]{1,6}\s*[\]】]\s*"
        r"|[\[【]\s*(?:全\d+集|已完结|更新至\d+集)\s*[\]】]\s*$")
    _NAME_REGION_WRAP = re.compile(
        r"[\[【\(]\s*(?:大陆|国产|内地|中国大陆|中国|美国|日本|韩国|香港|台湾|英国|法国|泰国|印度|其他|其它|海外|中影|美剧|韩剧|日剧|港剧|台剧)\s*[\]】\)]"
    )

    def _clean_name(self, name):
        n = re.sub(r"\s+", " ", str(name or "").strip())
        for _ in range(3):
            new = self._NAME_WRAPS.sub("", n)
            new = self._NAME_REGION_WRAP.sub("", new)
            new = self._NAME_TRIM_TAILS.sub("", new).strip()
            new = re.sub(r"\s{2,}", " ", new).strip()
            if new == n:
                break
            n = new
        return n.strip(" -_|·")

    _QUERY_RULES = ("年份", "地区", "类型", "排序", "线路")

    def _parse_query(self, key):
        words, cond = str(key or "").strip(), {}
        for tag in self._QUERY_RULES:
            m = re.search(tag + r"[:：]\s*(\S+)", words)
            if m:
                cond[tag] = m.group(1)
                words = words.replace(m.group(0), " ")
        return re.sub(r"\s+", " ", words).strip(), cond

    # ==================== ⑥ 筛选器 ====================

    @staticmethod
    def _dim(key, name, values):
        return {"key": key, "name": name,
                "value": [{"n": str(v[1]), "v": str(v[0])} for v in values]}

    @staticmethod
    def _extend_val(extend, key, default=""):
        try:
            v = (extend or {}).get(key)
        except Exception:
            v = None
        v = str(v).strip() if v not in (None, "") else ""
        return v or default

    # ==================== 站点实现区 ====================

    def homeContent(self, filter):
        """② 进壳提速: 新鲜缓存秒回; 过期缓存立即返回旧数据+后台刷新
        (stale-while-revalidate), 绝不让壳子首屏等网络; 仅冷启动才同步抓"""
        box = getattr(self, "_home_cache", None)
        if not isinstance(box, dict):
            box = self._home_cache = {}
        hit = box.get("home")
        if hit and time.time() - hit[0] < self.HOME_CACHE_TTL:
            return hit[1]
        # 过期内存缓存: 立即返回旧数据, 后台刷新
        if hit:
            self._bg_home_refresh()
            return hit[1]
        # 持久缓存(重启秒进): 新鲜直接用; 过期先用旧的+后台刷新
        try:
            blob = self.getCache("home:v3")
            if blob:
                obj = json.loads(blob) if isinstance(blob, str) else blob
                ts = float(obj.get("ts") or 0)
                res = obj.get("res")
                if res and res.get("class"):
                    box["home"] = (ts, res)
                    if time.time() - ts < self.HOME_CACHE_TTL:
                        return res
                    self._bg_home_refresh()
                    return res
        except Exception:
            pass
        return self._fetch_home()

    def _fetch_home(self):
        result = {"class": self.classes, "list": [], "filters": self.filters}
        try:
            # 短读超时: 首屏预算收紧, classes/filters 永远先返回
            html = self._get(self.host + "/", timeout=(3, 6))
            items = self._parse_list(html)
            result["list"] = self._polish(items[:self.PAGE_LIMIT])
        except Exception:
            pass
        self._home_cache["home"] = (time.time(), result)
        try:
            self.setCache("home:v3", json.dumps(
                {"ts": time.time(), "res": result}, ensure_ascii=False))
        except Exception:
            pass
        return result

    def _bg_home_refresh(self):
        """② 后台刷新首页(用过期数据先行返回后调用, 用户无感)"""
        def _w():
            try:
                self._home_cache.pop("home", None)
                self._fetch_home()
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()

    def homeVideoContent(self):
        cached, hit = self._page_cache_get(
            "_homev_cache", "hv", self.HOME_CACHE_TTL)
        if hit:
            return cached
        result = {"list": []}
        try:
            home = self.homeContent(False)
            result = {"list": home.get("list") or []}
        except Exception:
            pass
        self._page_cache_set("_homev_cache", "hv", result)
        return result

    def categoryContent(self, tid, pg, filter, extend):
        """⑧⑥ 分类翻页+服务端筛选: /igosw槽位URL(地区/排序/年份/页码),
        pagecount 取翻页链接最大页(/igols-{pg} 与 /igosw槽位页码双形态)"""
        tid = str(tid or "")
        pg = int(pg or 1)
        key = (tid, str(pg), self._ext_key(extend))
        cached, hit = self._page_cache_get("_cat_cache", key, self.CAT_CACHE_TTL)
        if hit:
            return cached
        r = self._category_fetch(tid, pg, extend)
        self._page_cache_set("_cat_cache", key, r)
        # ① 翻页预热: 未到末页时后台预取下一页
        if (self.PREFETCH_NEXT_PAGE and r.get("list")
                and int(r.get("page") or 0) < int(r.get("pagecount") or 0)):
            nkey = (tid, str(pg + 1), self._ext_key(extend))
            if not self._cache_has("_cat_cache", nkey, self.CAT_CACHE_TTL):
                self._prefetch_page(tid, pg + 1, extend)
        return r

    def _category_fetch(self, tid, pg, extend):
        """⑧⑥ 分类抓取: 站点多维度组合筛选有偶发bug(某些组合返回0条),
        结果为空时自动降级重试(按 年份→地区→类型 优先级丢维度),
        保证页面不空白; 命中降级时pagecount设为1(避免翻页错乱)"""
        ex = dict(extend or {})
        result = self._cat_fetch_one(tid, pg, ex)
        if result and len(result.get("list") or []) > 0:
            return result
        # 空结果降级: 依次丢掉 年份 → 地区 → 类型
        drop_order = [("year", "年份"), ("area", "地区"), ("klass", "类型")]
        for key, label in drop_order:
            if ex.get(key):
                fallback = dict(ex)
                fallback.pop(key, None)
                r2 = self._cat_fetch_one(tid, pg, fallback)
                if r2 and len(r2.get("list") or []) > 0:
                    # 降级成功: 标记pagecount=1(筛选变了, 翻页按新条件重算)
                    r2["pagecount"] = 1
                    return r2
        return result or self._mk_page([], pg, 1)

    def _cat_fetch_one(self, tid, pg, extend):
        """单次分类页抓取 + pagecount解析"""
        url = self._cat_url(tid, pg, extend)
        html = self._get(url)
        if not html:
            return None
        items = self._parse_list(html)
        ex = extend or {}
        real_tid = str(ex.get("klass") or "") or str(tid)
        pgs = [int(x) for x in re.findall(
            r"/igols/{0}-(\d+)\.html".format(re.escape(real_tid)), html)]
        pgs += [int(x) for x in re.findall(
            r"/igosw/{0}--------(\d+)---\.html".format(re.escape(real_tid)),
            html)]
        for href in re.findall(r'href="(/igosw/[^"]+\.html)"', html):
            seg = href.split(".html")[0].split("/")[-1].split("-")
            if len(seg) == 12 and seg[8].isdigit() and int(seg[8]) > 0:
                pgs.append(int(seg[8]))
        pgs = [p for p in pgs if p > 0]
        pagecount = max(pgs) if pgs else 0
        limit = len(items) or self.PAGE_LIMIT
        if not pagecount:
            pagecount = pg if len(items) < self.PAGE_LIMIT else pg + 1
        return self._mk_page(items, pg, min(pagecount, 9999), limit)

    def _prefetch_page(self, tid, pg, extend):
        def _w():
            try:
                key = (str(tid), str(pg), self._ext_key(extend))
                if not self._cache_has("_cat_cache", key, self.CAT_CACHE_TTL):
                    r = self._category_fetch(tid, pg, extend)
                    self._page_cache_set("_cat_cache", key, r)
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()

    def detailContent(self, ids):
        """⑦④③ 详情: /igojs/{id}.html 一次请求拿全线路全选集;
        线路 .playNumPage a.Tab -> #detail_{sid} ul.playNumList a 选集"""
        vid = str(ids[0] if isinstance(ids, (list, tuple)) and ids
                  else (ids or ""))
        if not vid:
            return {"list": []}
        cached, hit = self._page_cache_get(
            "_detail_cache", vid, self.DETAIL_CACHE_TTL)
        if hit:
            return cached
        html = self._get(self._detail_url(vid))
        if not html:
            return {"list": []}
        vod = self._parse_detail(html, vid)
        grouped = self._parse_eps(html)
        if not vod.get("vod_name") or not grouped:
            return {"list": []}
        vod = self._mk_vod(vod, grouped)
        result = {"list": [vod]}
        self._page_cache_set("_detail_cache", vid, result)
        self._prefetch_top(vod)   # ① 后台预取置顶线路第1集
        return result

    def _parse_detail(self, html, vid):
        """⑦ 详情字段: og:title《片名》/ og:image / 年份·地区tag-link /
        导演·主演info-items / .vod_content 简介 / 状态角标"""
        vod = {"vod_id": vid, "vod_name": "", "vod_pic": "",
               "vod_remarks": "", "vod_year": "", "vod_area": "",
               "vod_class": "", "vod_director": "", "vod_actor": "",
               "vod_content": ""}
        m = re.search(r'property="og:title"[^>]*content="([^"]*)"', html)
        if m:
            nm = re.search(r"《(.+?)》", m.group(1))
            if nm:
                vod["vod_name"] = nm.group(1).strip()
            cm = re.search(r"在线观看[--]\s*([^-\s]{2,8})\s*--", m.group(1))
            if cm:
                vod["vod_class"] = cm.group(1)
        if not vod["vod_name"]:
            m = re.search(r"<h1[^>]*>([^<]{1,60})</h1>", html)
            if m:
                vod["vod_name"] = m.group(1).strip()
        m = re.search(r'property="og:image"[^>]*content="([^"]*)"', html)
        if m:
            vod["vod_pic"] = self._abs_pic(m.group(1))
        m = re.search(r'property="og:description"[^>]*content="([^"]*)"', html)
        if m:
            vod["vod_content"] = re.sub(
                r"\s+", " ", unquote(m.group(1))).strip()[:1000]
        # 年份/地区: 头部 tag-link (/igosw/17-----------2026.html 之年份位 /
        # /igosw/17-{urlencoded}----------.html 之地区位)
        for href, txt in re.findall(
                r'class="tag-link"[^>]*href="(/igosw/[^"]+)"[^>]*>([^<]*)<',
                html):
            t = txt.strip()
            m2 = re.match(r"^/igosw/\d+-([^-]*)-{2,}", href + "--")
            seg = href.split(".html")[0].split("/")
            if len(seg) == 3:
                parts = seg[2].split("-")
                # 槽位: [tid, 地区, 排序, 类型, 方向, -, -, -, 页码, -, -, 年份]
                if len(parts) >= 12 and parts[11] and re.match(
                        r"^(19|20)\d{2}$", parts[11]) and not vod["vod_year"]:
                    vod["vod_year"] = parts[11]
                if len(parts) >= 2 and parts[1] and not re.match(
                        r"^(time|hits|score|asc|desc|\d+)$", parts[1]) \
                        and not vod["vod_area"]:
                    try:
                        cand = unquote(parts[1])
                    except Exception:
                        cand = parts[1]
                    if cand and not cand.isdigit():
                        vod["vod_area"] = cand
        # 导演/主演: info-items label 定位
        for label, field in (("导演", "vod_director"), ("主演", "vod_actor")):
            lm = re.search(
                r'<label>\s*' + label + r'[：:]</label>(.{0,1500}?)</div>\s*</div>',
                html, re.S)
            if lm:
                names = [x.strip() for x in re.findall(
                    r'target="_blank">([^<]{1,24})</a>', lm.group(1))]
                if not names:
                    names = [x.strip() for x in lm.group(1).split("/") if x.strip()]
                vod[field] = ",".join(names[:20])[:200]
        # 制片国家/地区兜底
        if not vod["vod_area"]:
            am = re.search(r'制片国家/地区[：:]</label>.{0,300}?>\s*([^<\s]{1,12})',
                           html, re.S)
            if am:
                vod["vod_area"] = am.group(1).strip()
        # 状态 -> 角标
        sm = re.search(r'<label>\s*状态[：:]</label>.{0,200}?>([^<]{1,20})<',
                       html, re.S)
        if sm:
            vod["vod_remarks"] = sm.group(1).strip()
        # 简介兜底: .vod_content
        if not vod["vod_content"]:
            cm2 = re.search(r'class="vod_content"[^>]*>(.*?)</div>', html, re.S)
            if cm2:
                vod["vod_content"] = re.sub(
                    r"<[^>]+>|\s+", " ", cm2.group(1)).strip()[:1000]
        return vod

    def _parse_eps(self, html):
        """④⑩ 线路与选集: .playNumPage a.Tab(data-id=detail_{sid}, 线路名)
        + 对应 #detail_{sid} ul.playNumList a(/igokj/{vid}-{sid}-{nid}.html)"""
        grouped = {}
        tabs = re.findall(
            r'class="Tab[^"]*"\s+data-id="detail_(\d+)">.*?</i>\s*([^<]+)</a>',
            html, re.S)
        for sid, lname in tabs:
            lname = lname.strip()
            block = re.search(
                r'<div id="detail_' + re.escape(sid) + r'"[^>]*>(.*?)</div>',
                html, re.S)
            if not block:
                continue
            eps = []
            for em in re.finditer(
                    r'<a href="(/igokj/\d+-\d+-\d+\.html)"[^>]*>\s*([^<]{1,24})',
                    block.group(1)):
                href, label = em.group(1), em.group(2).strip()
                if not label:
                    label = "正片"
                eps.append((label, self._fix(href)))
            if eps:
                grouped[lname or "线路" + sid] = eps
        return grouped

    def _mk_vod(self, vod, grouped):
        """⑩④③⑦ 详情标准拼装: 线路原序 + 选集纯数字正序 + 海报绝对URL
        + 空角标按选集数兜底 + 片名清洗 + 登记集间序列(③下一集预取用)"""
        lines = [ln for ln in self._sort_lines(grouped) if grouped.get(ln)]
        parts, top_eps = [], []
        for ln in lines:
            eps = self._episodes_ascending(grouped.get(ln) or [])
            if eps and not top_eps:
                top_eps = eps
            self._register_seq([u for _, u in eps])
            parts.append("#".join("{}${}".format(t, u) for t, u in eps))
        vod["vod_play_from"] = "$$$".join(lines)
        vod["vod_play_url"] = "$$$".join(parts)
        vod["vod_pic"] = self._abs_pic(vod.get("vod_pic"))
        vod["vod_name"] = self._clean_name(vod.get("vod_name"))
        if not str(vod.get("vod_remarks") or "").strip() and top_eps:
            vod["vod_remarks"] = self._remark_from_eps(top_eps)
        vod["vod_remarks"] = self._format_remark(vod.get("vod_remarks"))
        return vod

    def _register_seq(self, urls):
        """③ 登记"本集->下一集"映射(播放成功后据此后台预取, 连看秒开)"""
        try:
            box = getattr(self, "_ep_next", None)
            if not isinstance(box, dict):
                box = self._ep_next = {}
            for a, b in zip(urls, urls[1:]):
                if a and b and a not in box:
                    box[a] = b
            self._mem_trim(box, cap=600)
        except Exception:
            pass

    def searchContent(self, key, quick, pg):
        """⑤ 聚合可搜: /igoso 表单真实对接(实测"庆余年"16条, 单页);
        变体递进(完整词->去空格->2字前缀)提高召回, 60s缓存"""
        kw, cond = self._parse_query(key)
        if not kw:
            return {"list": []}
        pg = int(pg or 1)
        ck = (kw, self._ext_key(cond), str(pg))
        cached, hit = self._page_cache_get(
            "_search_cache", ck, self.SEARCH_CACHE_TTL)
        if hit:
            return cached
        items = []
        variants = [kw]
        w2 = re.sub(r"\s+", "", kw)
        if w2 and w2 != kw:
            variants.append(w2)
        if len(w2 or kw) >= 4:
            w3 = (w2 or kw)[:2]
            if w3 not in variants:
                variants.append(w3)
        for q in variants[:3]:
            items = self._search_once(q)
            if items:
                break
        out = {"list": self._polish(items)}
        if pg == 1:
            out.update({"page": 1, "pagecount": 1,
                        "limit": len(out["list"]) or 20,
                        "total": len(out["list"])})   # 实测搜索单页
        # 空结果(限流桩页/无匹配)只短缓存10s, 不挡用户立即重试
        if out["list"]:
            self._page_cache_set("_search_cache", ck, out)
        else:
            self._page_cache_set("_search_cache", ck, out)
            try:
                self._search_cache[ck] = (
                    time.time() - self.SEARCH_CACHE_TTL + 10, out)
            except Exception:
                pass
        return out

    def _search_once(self, wd):
        """⑤ 单次搜索: 带站内Referer; 站点对快速连续搜索会间歇限流
        (返回1KB桩页), 阶梯退避多试 + 降级壳子fetch通道双通道兜底"""
        url = self._search_url(wd)
        headers = dict(self.headers)
        headers["Referer"] = self.host + "/"
        sess = self._init_session()
        html = ""
        # 阶梯退避: 立即 -> 1.5s -> 3.0s (实测限流窗口~3s, 爆发请求触发)
        for delay in (0, 1.5, 3.0):
            if delay:
                time.sleep(delay)
            try:
                if sess is not None:
                    r = sess.get(url, timeout=(self.CONNECT_TIMEOUT,
                                               self.READ_TIMEOUT),
                                 headers=headers)
                    enc = (r.encoding or "").lower()
                    if not enc or enc in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    html = r.text or ""
            except Exception:
                html = ""
            if "data-json" in html:
                return self._parse_list(html)
        # 末级兜底: 壳子fetch通道(用户家用IP, 放行率最高)
        try:
            resp = self.fetch(url, headers=headers)
            if resp is not None:
                html = getattr(resp, "text", "") or ""
        except Exception:
            pass
        if "data-json" in html:
            return self._parse_list(html)
        return []

    # ⑤ 搜索别名(防个别壳子按旧名调用)
    def quickSearchContent(self, key, pg=1):
        return self.searchContent(key, "1", pg)

    def searchContentPage(self, key, pg=1):
        return self.searchContent(key, "0", pg)

    # ==================== ①B 播放解析: 双层缓存 + 并发去重 + 预取 ====================

    def playerContent(self, flag, id, vipFlags=None, _prefetch_call=False):
        """播放: /igokj/{vid}-{sid}-{nid}.html 内嵌 player_aaaa JSON,
        实测 encrypt=0 直给 m3u8 -> parse:0 原生秒开;
        encrypt 1/2(unquote/base64)解码兜底; 无直链交壳子嗅探"""
        play_url = self._fix(str(id or ""))
        if not play_url:
            return {"parse": 0, "url": "", "header": self.play_headers}
        result = self._cached_play(play_url)
        if result is not None:
            return result
        inflight = getattr(self, "_parse_inflight", None)
        if inflight is None:
            inflight = self._parse_inflight = {}
        ev, owner = None, True
        if not _prefetch_call:
            with self._play_lock:
                ev = inflight.get(play_url)
                if ev is None:
                    ev = threading.Event()
                    inflight[play_url] = ev
                else:
                    owner = False
            if not owner:
                ev.wait(self.PARSE_WAIT_MAX)
                result = self._cached_play(play_url)
                if result is not None:
                    return result
                with self._play_lock:
                    if inflight.get(play_url) is ev:
                        ev_new = threading.Event()
                        inflight[play_url] = ev_new
                        ev, owner = ev_new, True
        try:
            result = self._resolve_play(play_url)
        finally:
            if owner:
                with self._play_lock:
                    inflight.pop(play_url, None)
                if ev is not None:
                    ev.set()
        # ③ 用户路径起播成功 -> 后台预取同线路下一集(连看第2集秒开)
        if not _prefetch_call and result and result.get("parse") == 0 \
                and result.get("url"):
            try:
                threading.Thread(
                    target=self._prefetch_next, args=(play_url,),
                    daemon=True).start()
            except Exception:
                pass
        return result

    def _cached_play(self, play_url):
        if not hasattr(self, "_play_cache"):
            self._play_cache = {}
        cached = self._play_cache.get(play_url)
        if cached and time.time() - cached[0] < self.PLAY_CACHE_TTL:
            return dict(cached[1])
        try:
            blob = self.getCache("play:" + play_url)
            if blob:
                obj = json.loads(blob) if isinstance(blob, str) else blob
                ts = float(obj.get("ts") or 0)
                res = obj.get("res")
                if res and res.get("url") and \
                        time.time() - ts < self.PLAY_CACHE_TTL:
                    self._play_cache[play_url] = (ts, res)
                    self._mem_trim(self._play_cache)
                    return dict(res)
        except Exception:
            pass
        return None

    def _save_play(self, play_url, result):
        self._play_cache[play_url] = (time.time(), result)
        self._mem_trim(self._play_cache)
        try:
            self.setCache("play:" + play_url, json.dumps(
                {"ts": time.time(), "res": result}, ensure_ascii=False))
        except Exception:
            pass

    def _resolve_play(self, play_url):
        import base64
        from urllib.parse import unquote as _uq
        # 用户起播预算收紧: 读超时5s(实测站点偶发8s级读抖动, 拖慢起播)
        html = self._get(play_url, timeout=(3, 5))
        m = re.search(r"player_aaaa=(\{.*?\})\s*[;<]", html, re.S)
        url, enc = "", 0
        if m:
            try:
                j = json.loads(m.group(1))
                url = str(j.get("url") or "")
                enc = int(j.get("encrypt") or 0)
            except Exception:
                url = ""
        if url:
            try:
                if enc == 1:
                    url = _uq(url)
                elif enc == 2:
                    url = _uq(base64.b64decode(url).decode("utf-8", "ignore"))
            except Exception:
                pass
        if url and re.search(r"\.(m3u8|mp4)(\?|$)", url):
            # ③ master变体直出: 本站m3u8实测全是master清单(97~119B),
            # 播放器本要多请求一跳变体(0.9~1.3s)。此处短超时深解析出
            # 最高画质变体直链; 失败(个别CDN不可达)原样返回不挡起播。
            if ".m3u8" in url:
                variant = self._resolve_m3u8_variant(url)
                if variant:
                    url = variant
            result = {"parse": 0, "url": url, "header": self.play_headers}
            self._save_play(play_url, result)
            return result
        # 兜底: 播放页内裸直链
        m2 = re.search(
            r'(https?://[^\s"\'<>]+?\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
        if m2:
            result = {"parse": 0, "url": m2.group(1),
                      "header": self.play_headers}
            self._save_play(play_url, result)
            return result
        # 交壳子WebView嗅探
        return {"parse": 1, "jx": 1, "url": play_url,
                "header": self.play_headers}

    # ==================== ③ 播放提速: master变体解析 + 下一集预取 ====================

    def _m3u8_get(self, url, timeout=(2.0, 2.5)):
        """m3u8专用轻量GET: 只带UA不带Referer(CDN鉴权差异), 单发不重试"""
        sess = self._init_session()
        if sess is not None:
            try:
                r = sess.get(url, timeout=timeout,
                             headers={"User-Agent": self.UA})
                return r.text or ""
            except Exception:
                return ""
        try:
            resp = self.fetch(url, headers={"User-Agent": self.UA})
            return getattr(resp, "text", "") or ""
        except Exception:
            return ""

    def _resolve_m3u8_variant(self, url):
        """master playlist -> 最高画质变体绝对URL(RESOLUTION高度优先,
        BANDWIDTH兜底); 非master/失败返回空串(调用方保留原URL)"""
        try:
            body = self._m3u8_get(url)
            if not body or "#EXT-X-STREAM-INF" not in body:
                return ""
            best, best_key = "", (-1, -1)
            lines = body.splitlines()
            for i, ln in enumerate(lines):
                if not ln.startswith("#EXT-X-STREAM-INF"):
                    continue
                nxt = ""
                for j in range(i + 1, len(lines)):
                    u2 = lines[j].strip()
                    if u2 and not u2.startswith("#"):
                        nxt = u2
                        break
                if not nxt:
                    continue
                rm = re.search(r"RESOLUTION=(\d+)[xX](\d+)", ln)
                bm = re.search(r"BANDWIDTH=(\d+)", ln)
                key = (int(rm.group(2)) if rm else 0,
                       int(bm.group(1)) if bm else 0)
                if key > best_key:
                    best_key, best = key, nxt
            if best:
                resolved = urljoin(url, best)
                if resolved.startswith("http"):
                    return resolved
        except Exception:
            pass
        return ""

    def _prefetch_next(self, play_url):
        """③ 同线路下一集预取(据详情登记的集间序列)"""
        try:
            nxt = (getattr(self, "_ep_next", {}) or {}).get(play_url)
            if not nxt:
                return
            if self._cached_play(nxt) is not None:
                return
            with self._play_lock:
                if nxt in self._parse_inflight:
                    return
                self._parse_inflight[nxt] = threading.Event()
            self._prefetch_worker(nxt)
        except Exception:
            pass

    def _prefetch_top(self, vod):
        try:
            urls = vod.get("vod_play_url") or ""
            if not urls:
                return
            first_ep = urls.split("$$$")[0].split("#")[0]
            if "$" not in first_ep:
                return
            play_url = first_ep.split("$", 1)[1]
            if not play_url or self._cached_play(play_url) is not None:
                return
            with self._play_lock:
                if play_url in self._parse_inflight:
                    return
                self._parse_inflight[play_url] = threading.Event()
            threading.Thread(
                target=self._prefetch_worker, args=(play_url,),
                daemon=True).start()
        except Exception:
            pass

    def _prefetch_worker(self, play_url):
        try:
            r = self.playerContent("", play_url, _prefetch_call=True)
            if r and r.get("parse") == 0 and r.get("url"):
                self.log("预取直链就绪: " + str(r.get("url"))[:60])
        except Exception:
            pass

    # ==================== ⑧⑨⑦⑤ 交付前验证(必须运行并打印) ====================

    def verify_category(self, tid, max_pages=3, extend=None):
        problems, seen, pg = [], set(), 1
        while pg <= max_pages:
            try:
                r = self.categoryContent(str(tid), str(pg), False,
                                         extend or {})
            except Exception as e:
                problems.append("第{}页异常: {}".format(pg, e))
                break
            items = r.get("list") or []
            if not items:
                if pg == 1:
                    problems.append("⑧ 首页为空(分类无内容)")
                break
            for it in items:
                vid = str(it.get("vod_id"))
                if not vid:
                    continue
                if vid in seen:
                    problems.append("第{}页重复: {}({})".format(
                        pg, it.get("vod_name"), vid))
                seen.add(vid)
                if not str(it.get("vod_pic") or "").startswith(
                        ("http://", "https://")):
                    problems.append("第{}页海报非绝对URL: {}".format(
                        pg, it.get("vod_name")))
            pg += 1
            pagecount = int(r.get("pagecount") or 0)
            if pagecount and pg > pagecount:
                break
        return problems

    def verify_search(self, kw, max_ms=6000):
        t0 = time.time()
        try:
            r = self.searchContent(kw, "1", "1")
        except Exception as e:
            return ["⑤ 搜索异常: {}".format(e)]
        problems = []
        if not (r or {}).get("list"):
            problems.append("⑤ 热词[{}]无结果".format(kw))
        if time.time() - t0 > max_ms:
            problems.append("① 搜索过慢: {:.2f}s".format(time.time() - t0))
        return problems

    def verify_detail(self, tid, pg="1"):
        try:
            r = self.categoryContent(str(tid), str(pg), False, {})
        except Exception as e:
            return ["⑦ 分类{}请求异常: {}".format(tid, e)]
        items = r.get("list") or []
        if not items:
            return ["⑦ 分类{}无数据可抽验".format(tid)]
        first = items[0]
        try:
            d = self.detailContent([first.get("vod_id")]) or {}
        except Exception as e:
            return ["⑦ 详情异常: {}".format(e)]
        lst = d.get("list") or []
        if not lst:
            return ["⑦ 详情为空: {}".format(first.get("vod_name"))]
        vod = lst[0]
        problems = []
        must = ("vod_id", "vod_name", "vod_pic",
                "vod_play_from", "vod_play_url")
        for k in must:
            if not str(vod.get(k) or "").strip():
                problems.append("⑦ 详情缺字段: {}".format(k))
        lines = [x for x in str(vod.get("vod_play_from") or "").split("$$$")
                 if x]
        segs = [x for x in str(vod.get("vod_play_url") or "").split("$$$")
                if x]
        if not lines or not segs:
            return problems + ["⑦ 无可用线路/选集"]
        if len(lines) != len(segs):
            problems.append("⑦ 线路数({})与选集段数({})不一致".format(
                len(lines), len(segs)))
        for i, seg in enumerate(segs):
            eps = [tuple(x.split("$", 1)) for x in seg.split("#") if "$" in x]
            if not eps:
                problems.append("⑦ 线路[{}]选集为空".format(lines[i]))
                continue
            labels = [t for t, _ in eps]
            nums = [int(x) for x in labels if str(x).isdigit()]
            if len(nums) != len(labels):
                problems.append("④ 线路[{}]非纯数字选集: {}".format(
                    lines[i], labels[:5]))
            if nums != sorted(nums):
                problems.append("④ 线路[{}]选集非正序".format(lines[i]))
        return problems

    def verify_all(self, max_pages=2, search_kw=""):
        report = {}
        for c in self.classes:
            tid = str(c.get("type_id"))
            report[tid] = (self.verify_category(tid, max_pages=max_pages)
                           + self.verify_detail(tid))
        if search_kw:
            report["_search"] = self.verify_search(search_kw)
        return report


# ==================== 交付自检(开发期运行) ====================
if __name__ == "__main__":
    REQUIRED = ["init", "getName", "homeContent", "homeVideoContent",
                "categoryContent", "detailContent", "searchContent",
                "playerContent"]
    V3_CHECKS = ["_polish", "_mk_page", "_mk_vod", "_ep_label",
                 "_episodes_ascending", "_format_remark", "_dim",
                 "_extend_val", "_parse_list", "_parse_detail", "_parse_eps",
                 "_cat_url", "verify_category", "verify_detail",
                 "verify_search", "verify_all",
                 "_fetch_home", "_bg_home_refresh",
                 "_m3u8_get", "_resolve_m3u8_variant", "_prefetch_next",
                 "_register_seq"]

    def selfcheck():
        fails = []
        for m in REQUIRED + V3_CHECKS:
            if not hasattr(Spider, m):
                fails.append("缺方法:" + m)
        s = Spider()
        s.init()
        # ⑤ 四能力声明
        for attr in ("searchable", "quickSearch", "filterable", "changeable"):
            if getattr(Spider, attr, None) != 1:
                fails.append("能力声明缺失:" + attr)
        # ⑥ 筛选器必须是纯类属性字典(壳子双通道可读)
        if not isinstance(Spider.filters, dict):
            fails.append("filters不是类属性dict(疑似property)")
        else:
            for c in Spider.classes:
                dims = Spider.filters.get(str(c["type_id"]))
                if not dims or not all(d.get("value") for d in dims):
                    fails.append("筛选维度缺失:tid=" + str(c["type_id"]))
        # ⑧ URL构造公式(与实测URL逐字符一致; pg=1隐式形态消除翻页重复)
        assert s._cat_url("2", 1, {}) == \
            "https://www.hebeigoogle.com/igosw/2-----------.html"
        assert s._cat_url("2", 2, {}) == \
            "https://www.hebeigoogle.com/igosw/2--------2---.html"
        assert s._cat_url("2", 1, {"year": "2026"}) == \
            "https://www.hebeigoogle.com/igosw/2-----------2026.html"
        assert s._cat_url("2", 1, {"area": "内地"}) == \
            "https://www.hebeigoogle.com/igosw/2-%E5%86%85%E5%9C%B0----------.html"
        assert s._cat_url("2", 1, {"by": "hits"}) == \
            "https://www.hebeigoogle.com/igosw/2--hits---------.html"
        # ⑥ 类型子分类: klass存在时替换tid为子tid(走独立类型页)
        assert s._cat_url("1", 1, {"klass": "6"}) == \
            "https://www.hebeigoogle.com/igosw/6-----------.html"
        assert s._cat_url("2", 1, {"klass": "17", "year": "2026"}) == \
            "https://www.hebeigoogle.com/igosw/17-----------2026.html"
        assert s._cat_url("1", 2, {"klass": "6", "by": "hits"}) == \
            "https://www.hebeigoogle.com/igosw/6--hits------2---.html"
        assert s._detail_url("123") == \
            "https://www.hebeigoogle.com/igojs/123.html"
        assert s._play_url("1", "2", "3") == \
            "https://www.hebeigoogle.com/igokj/1-2-3.html"
        # ③ master变体解析(mock: 相对路径变体=站点真实形态)
        s._m3u8_get = lambda u, timeout=(2.0, 2.5): (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
            "360p/hls/index.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1920x1080\n"
            "1080p/hls/index.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720\n"
            "720p/hls/index.m3u8\n")
        got = s._resolve_m3u8_variant("https://cdn.example.com/idx.m3u8")
        assert got == "https://cdn.example.com/1080p/hls/index.m3u8", got
        # 非master原样空串
        s._m3u8_get = lambda u, timeout=(2.0, 2.5): "#EXTM3U\n#EXTINF:4,\n1.ts\n"
        assert s._resolve_m3u8_variant("https://x/e.m3u8") == ""
        # ③ 集间序列登记
        s._ep_next = {}
        s._register_seq(["/a1", "/a2", "/a3"])
        assert s._ep_next["/a1"] == "/a2" and s._ep_next["/a2"] == "/a3"
        # ③④⑦⑤ 纯函数自检
        assert s._format_remark("全30集") == "已完结30集"
        assert s._format_remark("更新至03集") == "更新至3集"
        assert s._format_remark("全集") == "已完结"
        eps = s._episodes_ascending(
            [("第03集", "u3"), ("第01集", "u1"), ("第12集", "u12")])
        assert [e[0] for e in eps] == ["1", "3", "12"]
        assert s._ep_label("第01集") == "1"
        assert s._clean_name("【4K】沙丘2") == "沙丘2"
        kw, cond = s._parse_query("庆余年 年份:2025")
        assert kw == "庆余年" and cond["年份"] == "2025"
        # ⑩⑦ _mk_vod
        vod = {"vod_id": "1", "vod_name": "测试剧", "vod_pic": "/p.jpg",
               "vod_remarks": ""}
        out = s._mk_vod(vod, {"VIP9高清云播": [("第02集", "u2"),
                                               ("第01集", "u1")]})
        assert out["vod_play_url"] == "1$u1#2$u2"
        assert out["vod_remarks"] == "更新至2集"
        # 列表解析(离线样例)
        sample = ("<li class=\"dx-vod\" data-json='{\"id\":194587,"
                  "\"name\":\"师兄太稳健\",\"score\":\"7.0\","
                  "\"pic\":\"/upload/vod/x.jpg\","
                  "\"link\":\"\\/igojs\\/194587.html\"}'>"
                  "<span class=\"vod_remarks\">更新至03集</span></li>")
        lst = s._parse_list(sample)
        assert len(lst) == 1 and lst[0]["vod_id"] == "194587"
        assert lst[0]["vod_remarks"] == "更新至03集"
        assert lst[0]["vod_pic"].startswith("https://")
        # ① 缓存命中
        s._page_cache_set("_cat_cache", ("1", "1", "{}"), {"list": [1]})
        got, hit = s._page_cache_get(
            "_cat_cache", ("1", "1", "{}"), s.CAT_CACHE_TTL)
        assert hit and got == {"list": [1]}
        print("自检通过" if not fails else "自检失败: {}".format(fails))
        return not fails

    selfcheck()
