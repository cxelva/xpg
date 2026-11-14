# -*- coding: utf-8 -*-
# 人人视频 / RRSP 可用源（基于 mh.yichengwlkj.com / api.rrmj.plus）
# 修复：过滤非剧集卡片、统一封面/标题字段
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
import uuid

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

try:
    from base.spider import Spider as _Base
except Exception:
    class _Base:
        pass


class Spider(_Base):
    def getName(self):
        return '人人视频'

    def init(self, extend=''):
        self.host = 'api.rrmj.plus'
        self.ss = b'ES513W0B1CsdUrR13Qk5EgDAKPeeKZY'
        self.dk = b'3b744389882a4067'
        self.iv = b'b1da7878016e4e2b'
        self.ref = 'https://mh.yichengwlkj.com/'
        self.ua = ('Mozilla/5.0 (Linux; Android 16; PJX110) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36')
        # 分类：id -> (显示名, position)
        self.cate_map = {
            '36': ('精选', 'CHANNEL_INDEX'),
            '257': ('电影', 'CHANNEL_MOVIE'),
            '260': ('美剧', 'CHANNEL_USK'),
            '263': ('韩剧', 'CHANNEL_KR'),
            '655': ('动漫', 'CHANNEL_CHN'),
            '266': ('日剧', 'CHANNEL_JP'),
            '272': ('英剧', 'CHANNEL_UK'),
        }
        # 这些 sectionType 不是剧集列表，直接跳过
        self.skip_types = {
            'MAGIC_CUBE', 'TOP', 'BANNER', 'AD', 'INFO_FLOW',
            'NAVIGATION', 'ICON', 'CHANNEL'
        }

    def _rr(self, path, params=None):
        if params is None:
            params = {}
        ts = int(time.time() * 1000)
        dev = uuid.uuid4().hex
        qs_parts = []
        for k in sorted(params):
            qs_parts.append('%s=%s' % (k, urllib.parse.quote(str(params[k]), safe='')))
        qs = '&'.join(qs_parts)
        sign_str = 'GET\naliId:%s\nct:web_applet\ncv:1.0.0\nt:%s\n%s?%s' % (
            dev, ts, path, qs)
        sg = base64.b64encode(
            hmac.new(self.ss, sign_str.encode(), hashlib.sha256).digest()
        ).decode()
        url = 'https://%s%s' % (self.host, path)
        if qs:
            url += '?' + qs
        req = urllib.request.Request(url, headers={
            'x-ca-sign': sg,
            't': str(ts),
            'aliId': dev,
            'umid': dev,
            'deviceId': dev,
            'clientVersion': '1.0.0',
            'cv': '1.0.0',
            'clientType': 'web_applet',
            'ct': 'web_applet',
            'uet': '9',
            'User-Agent': self.ua,
            'Origin': self.ref[:-1],
            'Referer': self.ref,
        })
        body = urllib.request.urlopen(req, timeout=15).read()
        try:
            dec = unpad(
                AES.new(self.dk, AES.MODE_ECB).decrypt(base64.b64decode(body)), 16
            ).decode()
            return json.loads(dec)
        except Exception:
            try:
                return json.loads(body.decode('utf-8', 'replace'))
            except Exception:
                return {}

    def _proxy_pic(self, pic):
        """把防盗链图片转成走本地代理，壳子才能显示"""
        if not pic:
            return ''
        if pic.startswith('http://'):
            pic = 'https://' + pic[7:]
        # FongMi / OK影视 常用写法
        try:
            base = self.getProxyUrl()
        except Exception:
            base = ''
        if base:
            sep = '&' if '?' in base else '?'
            return f"{base}{sep}do=img&url={urllib.parse.quote(pic)}"
        # 兜底 proxy:// 协议
        return f"proxy://do=img&url={urllib.parse.quote(pic)}"

    def _pick_item(self, item):
        """从不同区块结构中统一取出剧集信息，非剧集返回 None"""
        # 必须有 dramaId
        did = item.get('dramaId')
        if did is None or did == '':
            # 搜索结果常用 id
            did = item.get('id')
        if did is None or did == '':
            return None
        did = str(did)

        # 标题：兼容多种字段
        title = (
            item.get('title')
            or item.get('dramaTitle')
            or item.get('name')
            or item.get('subTitle')
            or ''
        )
        title = str(title).strip()
        # 过滤明显不是剧名的短词
        if not title or title in ('全部', '全部分类', '排行榜', '电影', '更多'):
            return None
        if len(title) <= 1:
            return None

        # 封面：兼容多种字段
        pic = (
            item.get('cover')
            or item.get('verticalCover')
            or item.get('coverUrl')
            or item.get('cover3Url')
            or item.get('cover3')
            or item.get('imgUrl')
            or item.get('mobileImgUrl')
            or ''
        )
        if isinstance(pic, dict):
            pic = pic.get('url') or ''
        pic = str(pic).strip()
        pic = self._proxy_pic(pic)

        remarks = (
            item.get('recommendInfo')
            or item.get('cornerMark')
            or item.get('score')
            or item.get('year')
            or item.get('playStatus')
            or ''
        )
        remarks = str(remarks).strip()

        return {
            'vod_id': did,
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': remarks,
        }

    def _extract_list(self, data):
        """从 page 接口结果中提取剧集列表"""
        videos = []
        seen = set()
        sections = (data.get('data') or {}).get('sections') or []
        for sec in sections:
            stype = (sec.get('sectionType') or '').upper()
            if stype in self.skip_types:
                continue
            for item in sec.get('sectionContents') or []:
                card = self._pick_item(item)
                if not card:
                    continue
                if card['vod_id'] in seen:
                    continue
                seen.add(card['vod_id'])
                videos.append(card)
        return videos

    def homeContent(self, filter):
        classes = [
            {'type_id': k, 'type_name': v[0]}
            for k, v in self.cate_map.items()
        ]
        return {'class': classes, 'filters': {}}

    def homeVideoContent(self):
        data = self._rr('/m-station/app/page', {
            'position': 'CHANNEL_INDEX',
            'pageNum': 1,
            'personalRecommend': 0,
        })
        return {'list': self._extract_list(data)}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        pos = self.cate_map.get(str(tid), ('精选', 'CHANNEL_INDEX'))[1]
        data = self._rr('/m-station/app/page', {
            'position': pos,
            'pageNum': page,
            'personalRecommend': 0,
        })
        videos = self._extract_list(data)
        return {
            'list': videos,
            'page': page,
            'pagecount': 9999 if videos else page,
            'limit': 20,
            'total': 999999,
        }

    def searchContent(self, key, quick, pg='1'):
        page = int(pg) if str(pg).isdigit() else 1
        data = self._rr('/m-station/search/drama', {
            'keywords': key,
            'pageNum': page,
            'pageSize': 20,
        })
        videos = []
        for item in (data.get('data') or {}).get('searchDramaList') or []:
            card = self._pick_item(item)
            if card:
                # 搜索结果里 id 字段是剧集 id
                if not card['vod_id'] or card['vod_id'] == 'None':
                    card['vod_id'] = str(item.get('id') or '')
                if card['vod_id']:
                    videos.append(card)
        return {
            'list': videos,
            'page': page,
            'pagecount': 9999 if videos else page,
            'limit': 20,
            'total': 999999,
        }

    def detailContent(self, ids):
        did = str(ids[0])
        data = self._rr('/m-station/drama/page', {
            'hsdrOpen': 0,
            'isAgeLimit': 0,
            'dramaId': did,
            'pageNum': 1,
            'pageSize': 300,
        })
        d = data.get('data') or {}
        info = d.get('dramaInfo') or {}
        if not info:
            return {'list': []}

        eps = d.get('episodeList') or []
        play_list = []
        for e in eps:
            no = e.get('episodeNo') or (len(play_list) + 1)
            sid = e.get('sid') or ''
            if not sid:
                continue
            token = base64.b64encode(
                json.dumps({'d': did, 's': sid}, separators=(',', ':')).encode()
            ).decode()
            play_list.append('%s$%s' % (no, token))

        if not play_list:
            return {'list': []}

        title = info.get('title') or info.get('name') or ''
        pic = info.get('cover') or info.get('cover3Url') or info.get('coverUrl') or ''
        pic = self._proxy_pic(pic)
        return {
            'list': [{
                'vod_id': did,
                'vod_name': title,
                'vod_pic': pic,
                'vod_year': str(info.get('year') or ''),
                'vod_area': info.get('area') or '',
                'vod_remarks': info.get('playStatus') or info.get('serialStatus') or '',
                'vod_actor': info.get('actor') or '',
                'vod_director': info.get('director') or '',
                'vod_content': info.get('plotType') or info.get('subtitle') or info.get('shortDesc') or '',
                'vod_play_from': '人人视频',
                'vod_play_url': '#'.join(play_list),
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        try:
            j = json.loads(base64.b64decode(id + '=' * (-len(id) % 4)).decode())
            did, sid = j.get('d', ''), j.get('s', '')
            if not did or not sid:
                return {'parse': 0, 'url': '', 'header': {}}

            last = ''
            for q in ('HD', 'SD'):
                pl = self._rr('/m-station/drama/play', {
                    'hsdrOpen': 0,
                    'dramaId': did,
                    'episodeSid': sid,
                    'quality': q,
                    'hevcOpen': 0,
                    'tria4k': 0,
                })
                pd = pl.get('data') or {}
                m3 = pd.get('m3u8') or {}
                ns = pd.get('newSign') or ''
                if not m3.get('url') or len(ns) < 20:
                    continue
                try:
                    u = unpad(
                        AES.new(ns[4:20].encode(), AES.MODE_CBC, self.iv).decrypt(
                            base64.b64decode(m3['url'])
                        ), 16
                    ).decode()
                    if u.startswith('http'):
                        return {
                            'parse': 0,
                            'url': u,
                            'header': {
                                'User-Agent': self.ua,
                                'Referer': self.ref,
                            }
                        }
                    last = u
                except Exception:
                    continue
            if last:
                return {
                    'parse': 0,
                    'url': last,
                    'header': {'User-Agent': self.ua, 'Referer': self.ref}
                }
        except Exception:
            pass
        return {'parse': 0, 'url': '', 'header': {}}

    def isVideoFormat(self, url):
        u = url or ''
        return bool('.m3u8' in u or '.mp4' in u or 'auth_key=' in u)

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        # 代理防盗链封面图
        if str(param.get('do') or '') == 'img':
            url = param.get('url') or ''
            if not url:
                return [404, 'text/plain', b'']
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': self.ua,
                    'Referer': self.ref,
                })
                with urllib.request.urlopen(req, timeout=12) as r:
                    data = r.read()
                    ctype = r.headers.get('Content-Type') or 'image/jpeg'
                return [200, ctype, data]
            except Exception:
                return [404, 'text/plain', b'']
        return [200, 'text/plain', b'']
