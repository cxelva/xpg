# -*- coding: utf-8 -*-
# TVBox爬虫 - 58影视 (yoss.58sph5.com)
# by：小苹果影视

import json
import uuid
import base64
import hashlib
import sys
import urllib3
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "58影视"

    def init(self, extend=''):
        self.base_url = 'https://al01.ilovefhy.com'
        self.home_url = 'https://yoss.58sph5.com'
        self.error_url = 'https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/xgplayer_doc_video/mp4/xgplayer-demo-720p.mp4'
        self.def_headers = {
            'User-Agent': 'okhttp/4.12.0',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': self.home_url,
            'Referer': self.home_url + '/',
        }
        self.device_id = str(uuid.uuid4()).replace('-', '')
        self.uuid_val = ''
        self.secret = ''
        self.img_cdn = 'https://cstp.58ysapp.cn'  # 从 config 动态获取，此为兜底
        self.sess = requests.Session()
        self.sess.headers.update(self.def_headers)
        self.sess.verify = False
        self._auth()
        self._init_cdn()

    def getDependence(self):
        return ['pycryptodome']

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass

    # ========== 分类映射 ==========
    # type_list 来自 search 接口: movie/tv/variety/cartoon/short
    TYPE_MAP = {
        'movie':    '电影',
        'tv':       '电视剧',
        'variety':  '综艺',
        'cartoon':  '动漫',
        'short':    '短剧',
    }

    # ========== 分类 ==========

    def homeContent(self, filter):
        data = self._get('/v1/client/app/config')
        channel_data = data.get('data', {}).get('channel', {})
        # channel 结构: {data: [{is_home, list: [{id,name,...}]}]}
        ch_list = channel_data.get('data', [])
        classes = []
        if ch_list:
            # 取第一个 group 的 list（首页 tab）
            for ch in ch_list[0].get('list', []):
                if not ch.get('is_home'):  # 排除"首页"本身
                    classes.append({
                        'type_id': ch.get('name', ''),
                        'type_name': ch.get('name', ''),
                    })
        # 兜底
        if not classes:
            for tid, tname in self.TYPE_MAP.items():
                classes.append({'type_id': tid, 'type_name': tname})
        return {'class': classes}

    # ========== 首页推荐 ==========

    def homeVideoContent(self):
        # 后端没有专门的首页推荐接口，用搜索"1"（单字符搜索覆盖面广）模拟
        data = self._get('/v1/client/search/video', params={
            'keyword': '1', 'page': '1', 'page_size': '30',
        })
        items = data.get('data', {}).get('list', [])
        videos = self._arr2vods(items)
        # 去重
        seen = set()
        unique = []
        for v in videos:
            if v['vod_id'] not in seen:
                seen.add(v['vod_id'])
                unique.append(v)
        return {'list': unique[:24], 'parse': 0, 'jx': 0}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, ext):
        # tid = 分类名（如 "电影"）或 type（如 "movie"）
        type_val = tid
        # 如果传的是中文名，反查 type
        for k, v in self.TYPE_MAP.items():
            if tid == v:
                type_val = k
                break
        # 用搜索接口 + type 参数做分类筛选
        data = self._get('/v1/client/search/video', params={
            'keyword': '1', 'page': pg, 'page_size': '20', 'type': type_val,
        })
        items = data.get('data', {}).get('list', [])
        total = data.get('data', {}).get('total', 0)
        return {
            'list': self._arr2vods(items),
            'page': int(pg),
            'pagecount': max(1, (total + 19) // 20),
            'limit': 20,
            'total': total,
            'parse': 0, 'jx': 0,
        }

    # ========== 详情 ==========

    def detailContent(self, did):
        ids = did[0] if isinstance(did, list) else did
        data = self._get('/v1/client/video/video/video_detail', params={'video_id': ids})
        info = data.get('data', {})

        episode_list = info.get('episode_list', [])
        if not episode_list:
            return {'list': []}

        # 按语言/language 分线路
        from_map = {}
        for ep in episode_list:
            sources = ep.get('sources', [])
            for src in sources:
                lang = src.get('language', '') or '🍎小苹果影视'
                if not src.get('play_url'):
                    continue
                if lang not in from_map:
                    from_map[lang] = []
                from_map[lang].append(ep)

        froms = []
        urls_list = []
        for lang, eps in from_map.items():
            ep_strs = []
            for ep in eps:
                ep_title = ep.get('title', str(ep.get('episode', '')))
                src = None
                for s in ep.get('sources', []):
                    if s.get('play_url'):
                        src = s
                        break
                if not src:
                    continue
                ep_strs.append(f'{ep_title}${ids}-{ep["episode"]}')
            if ep_strs:
                froms.append(lang)
                urls_list.append('#'.join(ep_strs))

        vod_pic = ''
        cover_images = info.get('cover_images') or []
        if cover_images:
            vod_pic = cover_images[0].get('url', '')
        if not vod_pic:
            vod_pic = info.get('cover', '')
        if vod_pic and not vod_pic.startswith('http'):
            vod_pic = self.img_cdn + vod_pic

        vod = {
            'vod_id': ids,
            'vod_name': info.get('title', ''),
            'vod_pic': vod_pic,
            'vod_remarks': info.get('update_text', ''),
            'vod_year': str(info.get('year', '')),
            'vod_area': info.get('area', ''),
            'vod_actor': info.get('actors', ''),
            'vod_director': info.get('directors', ''),
            'vod_content': '🍎小苹果影视\n' + (info.get('intro', '') or ''),
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls_list),
            'type_name': info.get('category_name', ''),
        }
        return {'list': [vod], 'parse': 0, 'jx': 0}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, page='1'):
        data = self._get('/v1/client/search/video', params={
            'keyword': key, 'page': page, 'page_size': '20',
        })
        items = data.get('data', {}).get('list', [])
        total = data.get('data', {}).get('total', 0)
        return {
            'list': self._arr2vods(items),
            'page': int(page),
            'pagecount': max(1, (total + 19) // 20),
            'pagecount1': (total + 19) // 20,
            'limit': 20,
            'total': total,
            'parse': 0, 'jx': 0,
        }

    # ========== 播放 ==========

    def playerContent(self, flag, pid, vipFlags):
        try:
            parts = pid.split('-')
            video_id = parts[0]
            episode = parts[1]

            data = self._get('/v1/client/video/video/video_detail', params={'video_id': video_id})
            episode_list = data.get('data', {}).get('episode_list', [])

            target_ep = None
            for ep in episode_list:
                if str(ep.get('episode', '')) == str(episode):
                    target_ep = ep
                    break

            if not target_ep:
                return {'url': self.error_url, 'header': '', 'parse': 0, 'jx': 0}

            sources = target_ep.get('sources', [])
            src = None
            for s in sources:
                if s.get('play_url') and s.get('clarity_is_vip') != 1:
                    src = s
                    break
            if not src:
                src = next((s for s in sources if s.get('play_url')), None)

            if not src:
                return {'url': self.error_url, 'header': '', 'parse': 0, 'jx': 0}

            domain = src.get('domain', '')
            play_url = src.get('play_url', '')
            url = domain + play_url if domain and not play_url.startswith('http') else play_url

            return {
                'url': url,
                'header': {
                    'User-Agent': 'okhttp/4.12.0',
                    'Referer': self.home_url + '/',
                },
                'parse': 0, 'jx': 0,
            }
        except Exception as e:
            print(f'[58ys] playerContent error: {e}')
            return {'url': self.error_url, 'header': '', 'parse': 0, 'jx': 0}

    # ==========================================
    # 私有方法
    # ==========================================

    def _init_cdn(self):
        """从 config 接口获取图片 CDN 域名"""
        try:
            data = self._get('/v1/client/app/config')
            img_domain = data.get('data', {}).get('image_domain', '')
            if img_domain:
                self.img_cdn = img_domain.rstrip('/')
        except Exception:
            pass

    def _auth(self):
        """游客注册获取 uuid + secret"""
        try:
            self.sess.headers['X-Device-UUID'] = self.device_id
            r = self.sess.post(self.base_url + '/v1/client/auth/visitor/register', json={
                'app_version': '2.1.1',
                'device_id': self.device_id,
                'model': 'Web',
                'os_version': '0',
                'platform': 'Web',
                'source_domain': 'yoss.58sph5.com',
            }, timeout=10)
            resp = r.json()
            self.uuid_val = resp['data']['uuid']
            self.secret = resp['data']['secret']
            self.sess.headers['X-Device-UUID'] = self.uuid_val
            self.sess.headers['Authorization'] = f'Bearer {self.secret}'
        except Exception as e:
            print(f'[58ys] _auth error: {e}')

    def _get(self, path, params=None):
        """统一 GET 请求，自动处理加密响应"""
        try:
            r = self.sess.get(self.base_url + path, params=params, timeout=15)
            raw = r.text.strip()
            if raw.startswith('{') or raw.startswith('['):
                return r.json()
            if len(raw) == 0:
                return {}
            return json.loads(self._aes_ecb_decrypt(raw, self.secret))
        except Exception as e:
            print(f'[58ys] _get {path} error: {e}')
            return {}

    def _aes_ecb_decrypt(self, cipher_b64, secret):
        """AES-ECB-PKCS7 解密，key=SHA256(secret)"""
        key = hashlib.sha256(secret.encode()).digest()
        raw = base64.b64decode(cipher_b64)
        cipher = AES.new(key, AES.MODE_ECB)
        return unpad(cipher.decrypt(raw), AES.block_size).decode('utf-8')

    def _arr2vods(self, arr):
        """API 返回的列表项转 TVBox vod 格式"""
        data = []
        for item in arr:
            video = item.get('video', item)
            # 图片: coverImages[0].url 是相对路径，需拼接 CDN 域名
            pic = ''
            cover_images = video.get('cover_images') or video.get('coverImages') or []
            if cover_images:
                pic = cover_images[0].get('url', '')
            if not pic:
                pic = video.get('cover', '')
            if pic and not pic.startswith('http'):
                pic = self.img_cdn + pic
            data.append({
                'vod_id': str(video.get('id', '')),
                'vod_name': video.get('title', ''),
                'vod_pic': pic,
                'vod_remarks': video.get('update_text', '') or video.get('state', ''),
                'type_name': video.get('category_name', ''),
                'vod_year': str(video.get('year', '') or video.get('years', '')),
            })
        return data


if __name__ == '__main__':
    pass
