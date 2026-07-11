#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
段友影视 (snmwg.com) 爬虫 - TVBox/影视仓 Spider 插件
支持分类浏览、筛选（年份/字母/类型/地区/语言）、详情获取、播放链接解析
"""

import re
import json
import logging
import urllib.parse
import os
import sys
import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Spider(BaseSpider):
    """段友影视爬虫"""

    BASE_URL = "https://www.snmwg.com"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-S908U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    CATEGORY_MAP = {
        "1": {"name": "电影", "url": "/vodtype/dianying.html"},
        "2": {"name": "电视剧", "url": "/vodtype/dianshiju.html"},
        "3": {"name": "综艺", "url": "/vodtype/zongyi.html"},
        "4": {"name": "动漫", "url": "/vodtype/dongman.html"},
        "5": {"name": "短剧", "url": "/vodtype/duanju.html"},
        "6": {"name": "影视解说", "url": "/vodtype/yingshijieshuo.html"},
    }

    TYPE_MAP = {
        "dongzuo": "动作",
        "xiju": "喜剧",
        "aiqing": "爱情",
        "kexuan": "科幻",
        "kongbu": "恐怖",
        "juqing": "剧情",
        "zhanzheng": "战争",
        "donghua": "动画",
        "jilu": "记录",
        "qita": "其他",
    }

    AREA_MAP = {
        "dalu": "大陆",
        "xianggang": "香港",
        "taiwan": "台湾",
        "meiguo": "美国",
        "riben": "日本",
        "hanguo": "韩国",
        "yingguo": "英国",
        "faguo": "法国",
        "deguo": "德国",
        "eluosi": "俄罗斯",
        "qita": "其他",
    }

    LANG_MAP = {
        "guoyu": "国语",
        "yingyu": "英语",
        "riyu": "日语",
        "fayu": "法语",
        "hanyu": "韩语",
        "qita": "其他",
    }

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(self.HEADERS)

    def init(self, extend):
        """初始化"""
        pass

    def getName(self):
        return "段友影视"

    def _parse_ext(self, ext):
        """解析ext参数，兼容dict和JSON字符串格式"""
        if not ext:
            return {}
        if isinstance(ext, dict):
            return ext
        if isinstance(ext, str):
            try:
                return json.loads(ext)
            except Exception:
                return {}
        return {}

    def _get(self, url):
        """GET请求封装"""
        try:
            resp = self.session.get(url, timeout=30)
            resp.encoding = "utf-8"
            return resp
        except Exception as e:
            logger.error(f"请求失败 {url}: {e}")
            return None

    def homeContent(self, filter=False):
        """首页内容"""
        try:
            url = f"{self.BASE_URL}/"
            resp = self._get(url)
            if not resp:
                return {}
            
            classes = []
            for cate_id, cate_info in self.CATEGORY_MAP.items():
                classes.append({
                    "type_id": cate_id,
                    "type_name": cate_info["name"],
                })
            
            home_list = self._parse_home_videos(resp.text)
            
            return {
                "class": classes,
                "filters": self._get_filters(),
                "list": home_list,
            }
        except Exception as e:
            logger.error(f"获取首页失败: {e}")
            return {}

    def homeVideoContent(self):
        """首页视频内容"""
        home = self.homeContent()
        return {"list": home.get("list", [])}

    def _parse_home_videos(self, html):
        """从首页解析视频列表"""
        videos = []
        soup = BeautifulSoup(html, 'html.parser')
        
        items = soup.find_all('a', class_=re.compile(r'vodlist_thumb'))
        seen_ids = set()
        
        for item in items:
            href = item.get('href', '')
            vid_match = re.search(r'/voddetail/(\d+)\.html', href)
            if not vid_match:
                continue
            vid_id = vid_match.group(1)
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            
            title = item.get('title', '')
            poster = item.get('data-original', '') or item.get('src', '')
            
            remark_tag = item.find(class_=re.compile(r'pic_text'))
            remarks = remark_tag.get_text(strip=True) if remark_tag else ''
            
            if title:
                videos.append({
                    "vod_id": vid_id,
                    "vod_name": title,
                    "vod_pic": poster,
                    "vod_remarks": remarks,
                })
        
        return videos[:36]

    def _get_filters(self):
        """获取筛选配置"""
        filters = {}
        
        for cate_id in self.CATEGORY_MAP:
            filters[cate_id] = [
                {
                    "key": "type",
                    "name": "类型",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "动作", "v": "dongzuo"},
                        {"n": "喜剧", "v": "xiju"},
                        {"n": "爱情", "v": "aiqing"},
                        {"n": "科幻", "v": "kexuan"},
                        {"n": "恐怖", "v": "kongbu"},
                        {"n": "剧情", "v": "juqing"},
                        {"n": "战争", "v": "zhanzheng"},
                        {"n": "动画", "v": "donghua"},
                        {"n": "记录", "v": "jilu"},
                        {"n": "其他", "v": "qita"},
                    ]
                },
                {
                    "key": "lang",
                    "name": "语言",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "国语", "v": "guoyu"},
                        {"n": "英语", "v": "yingyu"},
                        {"n": "日语", "v": "riyu"},
                        {"n": "法语", "v": "fayu"},
                        {"n": "韩语", "v": "hanyu"},
                        {"n": "其他", "v": "qita"},
                    ]
                },
                {
                    "key": "year",
                    "name": "年份",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "2026", "v": "2026"},
                        {"n": "2025", "v": "2025"},
                        {"n": "2024", "v": "2024"},
                        {"n": "2023", "v": "2023"},
                        {"n": "2022", "v": "2022"},
                        {"n": "2021", "v": "2021"},
                        {"n": "2020", "v": "2020"},
                        {"n": "2019", "v": "2019"},
                        {"n": "2018", "v": "2018"},
                        {"n": "2017", "v": "2017"},
                        {"n": "2016", "v": "2016"},
                        {"n": "更早", "v": "2015"},
                    ]
                },
                {
                    "key": "letter",
                    "name": "字母",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "A", "v": "A"},
                        {"n": "B", "v": "B"},
                        {"n": "C", "v": "C"},
                        {"n": "D", "v": "D"},
                        {"n": "E", "v": "E"},
                        {"n": "F", "v": "F"},
                        {"n": "G", "v": "G"},
                        {"n": "H", "v": "H"},
                        {"n": "I", "v": "I"},
                        {"n": "J", "v": "J"},
                        {"n": "K", "v": "K"},
                        {"n": "L", "v": "L"},
                        {"n": "M", "v": "M"},
                        {"n": "N", "v": "N"},
                        {"n": "O", "v": "O"},
                        {"n": "P", "v": "P"},
                        {"n": "Q", "v": "Q"},
                        {"n": "R", "v": "R"},
                        {"n": "S", "v": "S"},
                        {"n": "T", "v": "T"},
                        {"n": "W", "v": "W"},
                        {"n": "X", "v": "X"},
                        {"n": "Y", "v": "Y"},
                        {"n": "Z", "v": "Z"},
                        {"n": "其他", "v": "0"},
                    ]
                },
                {
                    "key": "area",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "大陆", "v": "dalu"},
                        {"n": "香港", "v": "xianggang"},
                        {"n": "台湾", "v": "taiwan"},
                        {"n": "美国", "v": "meiguo"},
                        {"n": "日本", "v": "riben"},
                        {"n": "韩国", "v": "hanguo"},
                        {"n": "英国", "v": "yingguo"},
                        {"n": "法国", "v": "faguo"},
                        {"n": "德国", "v": "deguo"},
                        {"n": "俄罗斯", "v": "eluosi"},
                        {"n": "其他", "v": "qita"},
                    ]
                },
            ]
        
        return filters

    def categoryContent(self, tid, pg, filter, ext):
        """分类内容"""
        try:
            page = int(pg) if pg else 1
            type_id = str(tid)
            
            cate_info = self.CATEGORY_MAP.get(type_id)
            if not cate_info:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            
            ext_dict = self._parse_ext(ext)
            type_filter = ext_dict.get('type', '')
            lang_filter = ext_dict.get('lang', '')
            year_filter = ext_dict.get('year', '')
            letter_filter = ext_dict.get('letter', '')
            area_filter = ext_dict.get('area', '')
            
            if type_filter and type_filter in self.TYPE_MAP:
                type_filter = self.TYPE_MAP[type_filter]
            if area_filter and area_filter in self.AREA_MAP:
                area_filter = self.AREA_MAP[area_filter]
            if lang_filter and lang_filter in self.LANG_MAP:
                lang_filter = self.LANG_MAP[lang_filter]
            
            has_filter = any([type_filter, lang_filter, year_filter, letter_filter, area_filter])
            
            if has_filter:
                type_name = cate_info["url"].replace('/vodtype/', '').replace('.html', '')
                
                if year_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}-----------{year_filter}.html"
                elif type_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}---{urllib.parse.quote(type_filter)}--------.html"
                elif area_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}-{urllib.parse.quote(area_filter)}----------.html"
                elif lang_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}----{urllib.parse.quote(lang_filter)}-------.html"
                elif letter_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}------------{letter_filter}.html"
                else:
                    url = f"{self.BASE_URL}/vodshow/{type_name}-------------.html"
            else:
                url = self.BASE_URL + cate_info["url"]
            
            if page > 1:
                url = url.replace('.html', f'-{page}.html')
            
            resp = self._get(url)
            if not resp:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            
            videos = self._parse_category_videos(resp.text)
            pagecount = self._parse_total_pages(resp.text)
            
            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": 20,
                "total": len(videos) * pagecount,
            }
        except Exception as e:
            logger.error(f"获取分类内容失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
    
    def _parse_total_pages(self, html):
        """解析总页数"""
        patterns = [
            r'共有(\d+)页',
            r'共\s*(\d+)\s*页',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return int(match.group(1))
        return 100

    def _parse_category_videos(self, html):
        """解析分类页面视频列表"""
        videos = []
        soup = BeautifulSoup(html, 'html.parser')
        
        items = soup.find_all('a', class_=re.compile(r'vodlist_thumb'))
        seen_ids = set()
        
        for item in items:
            href = item.get('href', '')
            vid_match = re.search(r'/voddetail/(\d+)\.html', href)
            if not vid_match:
                continue
            vid_id = vid_match.group(1)
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            
            title = item.get('title', '')
            poster = item.get('data-original', '') or item.get('src', '')
            
            remark_tag = item.find(class_=re.compile(r'pic_text'))
            remarks = remark_tag.get_text(strip=True) if remark_tag else ''
            
            if title:
                videos.append({
                    "vod_id": vid_id,
                    "vod_name": title,
                    "vod_pic": poster,
                    "vod_remarks": remarks,
                })
        
        return videos

    def detailContent(self, ids):
        """详情内容"""
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = f"{self.BASE_URL}/voddetail/{vod_id}.html"
            resp = self._get(url)
            if not resp:
                return {"list": []}
            
            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')
            
            title = ''
            title_tag = soup.find('h2', class_='title')
            if not title_tag:
                title_tag = soup.find('h1')
            if title_tag:
                title = title_tag.get_text(strip=True)
            
            poster = ''
            thumb_a = soup.find('a', class_=re.compile(r'vodlist_thumb|thumb'))
            if thumb_a:
                poster = thumb_a.get('data-original', '') or thumb_a.get('href', '')
            if not poster:
                imgs = soup.find_all('img')
                for img in imgs:
                    src = img.get('src', '') or img.get('data-original', '')
                    if 'upload/vod' in src:
                        poster = src
                        break
            
            year = ''
            area = ''
            type_name = ''
            lang = ''
            
            hot_banner = soup.find(class_='hot_banner')
            if hot_banner:
                banner_text = hot_banner.get_text(strip=True)
                
                year_match = re.search(r'年份：(\d{4})', banner_text)
                if year_match:
                    year = year_match.group(1)
                
                area_match = re.search(r'地区：([^类型]+)', banner_text)
                if area_match:
                    area = area_match.group(1).strip()
                
                type_match = re.search(r'类型：([^状态]+)', banner_text)
                if type_match:
                    type_name = type_match.group(1).strip()
            
            actor = ''
            director = ''
            content = ''
            
            detail_list = soup.find(class_='detail_list')
            if detail_list:
                items = detail_list.find_all(['p', 'li', 'div'])
                for item in items:
                    text = item.get_text(strip=True)
                    if text.startswith('主演：'):
                        actor = text.replace('主演：', '').strip()
                    elif text.startswith('导演：'):
                        director = text.replace('导演：', '').strip()
                    elif text.startswith('简介：'):
                        content = text.replace('简介：', '').strip()
                        content = re.sub(r'详细\s*>$', '', content).strip()
            
            if not actor or not director:
                info_text = soup.get_text()
                if not actor:
                    actor_match = re.search(r'主演：([^\n简介导演]+)', info_text)
                    if actor_match:
                        actor = actor_match.group(1).strip()
                if not director:
                    director_match = re.search(r'导演：([^\n简介]+)', info_text)
                    if director_match:
                        director = director_match.group(1).strip()
                if not content:
                    intro_match = re.search(r'简介：([^\n详细]+)', info_text)
                    if intro_match:
                        content = intro_match.group(1).strip()
            
            if not content:
                intro_tag = soup.find(class_=re.compile(r'intro|content|desc'))
                if not intro_tag:
                    intro_tag = soup.find('p', class_=re.compile(r'info|detail'))
                if intro_tag:
                    content = intro_tag.get_text(strip=True)
            
            play_from_list, play_url_list = self._parse_play_sources(html, vod_id)
            
            remarks = ''
            remark_tag = soup.find(class_=re.compile(r'status|state'))
            if remark_tag:
                remarks = remark_tag.get_text(strip=True)
            
            vod_item = {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": poster,
                "type_name": type_name,
                "vod_year": year,
                "vod_area": area,
                "vod_lang": lang,
                "vod_remarks": remarks,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": content,
                "vod_play_from": '$$$'.join(play_from_list),
                "vod_play_url": '$$$'.join(play_url_list),
            }
            
            return {"list": [vod_item]}
        except Exception as e:
            logger.error(f"获取详情失败: {e}")
            return {"list": []}

    def _parse_play_sources(self, html, vod_id):
        """解析播放源和集数 - 正序排列"""
        play_from_list = []
        play_url_list = []
        
        play_links = re.findall(r'/vodplay/(\d+)-(\d+)-(\d+)\.html', html)
        
        sources = {}
        for vid, sid, nid in play_links:
            if sid not in sources:
                sources[sid] = []
            sources[sid].append((int(nid), f"/vodplay/{vid}-{sid}-{nid}.html"))
        
        source_names = {
            "1": "线路1",
            "2": "线路2",
            "3": "线路3",
            "4": "线路4",
        }
        
        for sid in sorted(sources.keys()):
            episodes = sources[sid]
            episodes = sorted(set(episodes), key=lambda x: x[0])
            
            from_name = source_names.get(sid, f"线路{sid}")
            play_from_list.append(from_name)
            
            urls = []
            for nid, link in episodes:
                full_url = self.BASE_URL + link
                urls.append(f"第{nid}集${full_url}")
            
            play_url_list.append('#'.join(urls))
        
        if not play_from_list and play_links:
            play_from_list = ["线路1"]
            episodes = sorted(set([(int(nid), f"/vodplay/{vid}-{sid}-{nid}.html") for vid, sid, nid in play_links]), key=lambda x: x[0])
            urls = []
            for nid, link in episodes:
                full_url = self.BASE_URL + link
                urls.append(f"第{nid}集${full_url}")
            play_url_list.append('#'.join(urls))
        
        return play_from_list, play_url_list

    def _get_m3u8_url(self, play_link):
        """从播放页获取m3u8链接"""
        try:
            url = self.BASE_URL + play_link
            resp = self._get(url)
            if not resp:
                return ""
            
            match = re.search(r'player_aaaa\s*=\s*({[^<]+})', resp.text)
            if match:
                try:
                    data = json.loads(match.group(1))
                    m3u8_url = data.get('url', '')
                    if m3u8_url:
                        return m3u8_url
                except Exception:
                    pass
            
            m3u8_match = re.search(r'https?[:][/][/][^\s"\'<>]+m3u8', resp.text)
            if m3u8_match:
                return m3u8_match.group(0)
            
            return ""
        except Exception as e:
            logger.warning(f"获取m3u8失败 {play_link}: {e}")
            return ""

    def playerContent(self, flag, id, vipFlags):
        """播放内容 - 返回m3u8链接，支持播放页解析"""
        try:
            play_url = urllib.parse.unquote(id) if id else ''
            
            if '/vodplay/' in play_url:
                play_link = play_url.replace(self.BASE_URL, '')
                m3u8_url = self._get_m3u8_url(play_link)
                if m3u8_url:
                    return {
                        "parse": 0,
                        "url": m3u8_url,
                    }
            
            return {
                "parse": 0,
                "url": play_url,
            }
        except Exception as e:
            logger.error(f"解析播放失败: {e}")
            return {"parse": 0, "url": ""}

    def searchContent(self, key, quick, pg):
        """搜索内容（网站有安全验证，暂时返回空结果）"""
        try:
            page = int(pg) if pg else 1
            encoded_key = urllib.parse.quote(key)
            url = f"{self.BASE_URL}/vodsearch/-------------.html?wd={encoded_key}"
            if page > 1:
                url += f"&page={page}"
            
            resp = self._get(url)
            if not resp:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            
            videos = self._parse_category_videos(resp.text)
            
            return {
                "list": videos,
                "page": page,
                "pagecount": 100,
                "limit": 20,
                "total": len(videos) * 100,
            }
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}


def main():
    """测试用例"""
    spider = Spider()
    
    print("=" * 60)
    print("【1】测试首页")
    print("=" * 60)
    home = spider.homeContent()
    print(f"分类数量: {len(home.get('class', []))}")
    for c in home.get('class', []):
        print(f"  {c['type_id']}: {c['type_name']}")
    print(f"推荐视频数: {len(home.get('list', []))}")
    
    print("\n" + "=" * 60)
    print("【2】测试分类列表 (电影)")
    print("=" * 60)
    cat = spider.categoryContent("1", "1", False, {})
    print(f"本页视频数: {len(cat.get('list', []))}")
    for v in cat.get('list', [])[:5]:
        print(f"  - {v['vod_name']} [{v['vod_remarks']}]")
    
    print("\n" + "=" * 60)
    print("【3】测试详情页")
    print("=" * 60)
    if cat.get('list'):
        first_id = cat['list'][0]['vod_id']
        detail = spider.detailContent([first_id])
        if detail.get('list'):
            d = detail['list'][0]
            print(f"标题: {d['vod_name']}")
            print(f"年份: {d['vod_year']}")
            print(f"地区: {d['vod_area']}")
            print(f"类型: {d['type_name']}")
            print(f"导演: {d['vod_director']}")
            print(f"主演: {d['vod_actor'][:50]}...")
            print(f"海报: {d['vod_pic'][:50]}...")
            print(f"播放源: {d['vod_play_from']}")
    
    print("\n" + "=" * 60)
    print("【4】测试播放解析")
    print("=" * 60)
    player = spider.playerContent("线路1", "https://www.snmwg.com/vodplay/89006-1-1.html", [])
    print(f"parse: {player.get('parse')}")
    print(f"url: {player.get('url')}")
    
    print("\n" + "=" * 60)
    print("【5】测试搜索")
    print("=" * 60)
    search = spider.searchContent("浮华镇", False, "1")
    print(f"搜索结果数: {len(search.get('list', []))}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
