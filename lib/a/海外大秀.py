# coding=utf-8
# !/usr/bin/python
import json
import sys
import html as html_lib
from requests import Session

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://sinparty.com"
        self.api_host = "https://api.sinparty.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://sinparty.com/',
            'Origin': 'https://sinparty.com',
        }
        self.session = Session()
        self.session.headers.update(self.headers)

    def getName(self):
        return "SinParty"

    def homeContent(self, filter):
        result = {}
        cateManual = {"精选": "all", "女生": "girls", "男生": "guys", "情侣": "couples", "变性人": "trans"}
        result['class'] = [{'type_name': k, 'type_id': v} for k, v in cateManual.items()]
        
        filters = {}
        filters["all"] = [{"key": "cat", "name": "排序", "value": [
            {"n": "全部", "v": ""}, {"n": "热门推荐", "v": "trending"}, {"n": "近期新人", "v": "new"}, {"n": "私人节目", "v": "status_private"}
        ]}]
        filters["girls"] = [{"key": "cat", "name": "标签", "value": [
            {"n": "全部", "v": ""}, {"n": "亚洲", "v": "asian"}, {"n": "成熟", "v": "mature"}, {"n": "大胸", "v": "big_boobs"}, {"n": "视角", "v": "pov"}
        ]}]
        filters["guys"] = [{"key": "cat", "name": "标签", "value": [
            {"n": "全部", "v": ""}, {"n": "肌肉", "v": "muscular"}, {"n": "亚洲男", "v": "asian"}, {"n": "熊系", "v": "bear"}, {"n": "少年", "v": "twink"}
        ]}]
        filters["trans"] = [{"key": "cat", "name": "标签", "value": [
            {"n": "全部", "v": ""}, {"n": "成熟", "v": "mature"}, {"n": "青少年", "v": "teen"}
        ]}]

        result['filters'] = filters
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        url = f"{self.api_host}/v2/web/live-cams/web-rtc"
        params = {"page": pg, "per_page": 40, "od": "desc"}
        
        if tid == "couples":
            params["category[]"] = "couples"
        elif tid == "trans":
            params["category[]"] = "trans"
        elif tid == "guys":
            params["gender[]"] = "m"
        else: 
            params["gender[]"] = "f"
            params["so"] = "has_straight"


        if extend.get('cat'):
            val = extend['cat']
            if val.startswith('status_'):
                params["status[]"] = val.replace('status_', '')
            else:
                
                params["trending[]"] = val
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            data = response.json().get('data', {})
            items = data.get('items', [])
            vlist = []
            for item in items:
                if 'creator_user_hash' in item:
                    vid = f"native|{item.get('creator_user_hash')}"
                    pic = item.get('thumbnail_url') or item.get('poster_set_template', '').replace('{size}', '360')
                    name = item.get('title')
                elif 'Nickname' in item:
                    vid = f"external|{item.get('Nickname')}"
                    pic = item.get('Thumbnail') or item.get('Snapshot')
                    name = item.get('Nickname')
                else: continue

                vlist.append({
                    'vod_id': vid, 'vod_name': name or 'Live', 'vod_pic': pic,
                    'vod_remarks': f"HOT:{item.get('viewers', '0')}"
                })
            result['list'] = vlist
            result['page'] = int(pg)
            result['total'] = data.get('total', 0)
        except:
            result['list'] = []
        return result

    def detailContent(self, ids):
        vid = ids[0]
        parts = vid.split('|')
        if len(parts) < 2: return {'list': []}
        mode, key = parts[0], parts[1]
        vod = {'vod_id': vid, 'vod_play_from': 'SinParty', 'vod_play_url': ''}
        try:
            if mode == 'external':
                ext_api = f"https://manifest-server.naiadsystems.com/live/s:{key}.json?vdc=true"
                sm_headers = {'User-Agent': self.headers['User-Agent'], 'Referer': 'https://sinpartylive.com/', 'sitedomain': 'sinpartylive.com', 'tenantid': 'SM'}
                res = self.session.get(ext_api, headers=sm_headers, timeout=10)
                if res.status_code == 200:
                    hls = res.json().get('formats', {}).get('mp4-hls', {})
                    p_url = hls.get('manifest') or (hls.get('encodings')[-1].get('location') if hls.get('encodings') else None)
                    if p_url: vod['vod_play_url'] = f"SM高清源${html_lib.unescape(p_url)}"
            else:
                api_url = f"{self.api_host}/v2/web/live-cams/web-rtc/{key}"
                res_data = self.session.get(api_url, timeout=5).json()
                p_url = res_data.get('data', {}).get('playback_url')
                if p_url: vod['vod_play_url'] = f"高清原画${p_url}"
            if not vod['vod_play_url']: vod['vod_play_url'] = "离线$http://0.0.0.0/off.mp4"
        except:
            vod['vod_play_url'] = "异常$http://0.0.0.0/error.mp4"
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': id, 'header': self.headers}