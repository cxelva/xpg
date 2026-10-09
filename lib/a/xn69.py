# -*- coding: utf-8 -*-
# xn69 WordPress Spider for FongMi / TVBox
# 首页、分类、搜索、分页、详情、HLS 播放
# 文件名：xn69.py

import re
import html
import requests

from urllib.parse import urljoin, quote, unquote, urlparse
from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "XN69视频"

    def init(self, extend=""):
        self.host = "https://xn--69-6tia3cb.net"
        self.player_host = "https://lumierecore.com"
        self.hls_host = "https://zyntravo8.online"

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
            "Referer": self.host + "/"
        })
        self.timeout = 20

        self.classes = [
            {"type_id": "home", "type_name": "首页"},
            {
                "type_id": "/category/%e0%b8%84%e0%b8%a5%e0%b8%b4%e0%b8%9b%e0%b8%ab%e0%b8%a5%e0%b8%b8%e0%b8%94/",
                "type_name": "คลิปหลุด"
            },
            {
                "type_id": "/category/onlyfans/",
                "type_name": "OnlyFans"
            },
            {
                "type_id": "/category/mlive/",
                "type_name": "MLive"
            },
            {
                "type_id": "/category/thlive/",
                "type_name": "ThLive"
            },
            {
                "type_id": "/category/jav/",
                "type_name": "JAV"
            },
            {
                "type_id": "/category/xxx/",
                "type_name": "XXX"
            },
            {
                "type_id": "/category/%e0%b8%ab%e0%b8%99%e0%b8%b1%e0%b8%87%e0%b9%82%e0%b8%9b%e0%b9%8a%e0%b9%84%e0%b8%97%e0%b8%a2/",
                "type_name": "หนังโป๊ไทย"
            },
            {
                "type_id": "/category/%e0%b9%80%e0%b8%ad%e0%b8%a7%e0%b8%b5%e0%b8%88%e0%b8%b5%e0%b8%99/",
                "type_name": "AV视频"
            },
            {
                "type_id": "/category/%e0%b8%ab%e0%b9%89%e0%b8%ad%e0%b8%87%e0%b9%80%e0%b8%8a%e0%b8%b7%e0%b8%ad%e0%b8%94/",
                "type_name": "ห้องเชือด"
            }
        ]

    def getDependence(self):
        return []

    def _get(self, url, params=None):
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()

            if (
                not response.encoding
                or response.encoding.lower() == "iso-8859-1"
            ):
                response.encoding = (
                    response.apparent_encoding or "utf-8"
                )

            return response.text
        except Exception:
            return ""

    def _clean(self, value):
        if not value:
            return ""
        value = html.unescape(value)
        value = re.sub(r"<[^>]+>", "", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    def _attr(self, tag, name):
        if not tag:
            return ""

        pattern = (
            r'\b' + re.escape(name) +
            r'\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))'
        )
        match = re.search(pattern, tag, re.I | re.S)

        if not match:
            return ""

        return html.unescape(
            match.group(1) or
            match.group(2) or
            match.group(3) or ""
        )

    def _meta(self, text, name):
        pattern = (
            r'<meta\b(?=[^>]*(?:property|name|itemprop)\s*=\s*["\']'
            + re.escape(name) +
            r'["\'])[^>]*>'
        )
        match = re.search(pattern, text, re.I | re.S)

        if match:
            return self._attr(match.group(0), "content")

        return ""

    def _absolute(self, url, base=None):
        if not url:
            return ""

        url = html.unescape(url.strip())

        if url.startswith("//"):
            url = "https:" + url

        return urljoin(base or self.host + "/", url)

    def _image(self, block, base=None):
        for attr in (
            "data-src",
            "data-lazy-src",
            "data-original",
            "src"
        ):
            pattern = (
                r'<img\b[^>]*\b' + attr +
                r'\s*=\s*(["\'])(.*?)\1'
            )
            match = re.search(pattern, block, re.I | re.S)

            if match:
                value = html.unescape(match.group(2)).strip()

                if value and not value.startswith("data:image"):
                    return self._absolute(value, base)

        return ""

    def _is_detail_url(self, url):
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()

            if host not in (
                "xn--69-6tia3cb.net",
                "www.xn--69-6tia3cb.net"
            ):
                return False

            path = parsed.path.rstrip("/")

            if not path or path == "/":
                return False

            if re.search(r"/page/\d+$", path):
                return False

            if path.startswith((
                "/category/",
                "/tag/",
                "/wp-"
            )):
                return False

            return True
        except Exception:
            return False

    def _cards(self, text, base=None):
        result = []
        seen = set()

        pattern = (
            r'<a\b(?=[^>]*class=["\'][^"\']*post-video[^"\']*["\'])'
            r'[^>]*>.*?</a\s*>'
        )

        for match in re.finditer(pattern, text, re.I | re.S):
            block = match.group(0)
            opening = re.match(r'<a\b[^>]*>', block, re.I | re.S)

            if not opening:
                continue

            tag = opening.group(0)
            href = self._absolute(self._attr(tag, "href"), base)
            title = self._clean(self._attr(tag, "title"))

            if not title:
                title_match = re.search(
                    r'<h[1-6]\b[^>]*>(.*?)</h[1-6]\s*>',
                    block,
                    re.I | re.S
                )
                if title_match:
                    title = self._clean(title_match.group(1))

            image = self._image(block, base)

            if (
                not href
                or not title
                or not self._is_detail_url(href)
                or href in seen
            ):
                continue

            seen.add(href)
            result.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": image,
                "vod_remarks": ""
            })

        # 兼容搜索页的普通链接卡片
        if not result:
            for match in re.finditer(
                r'<a\b[^>]*>.*?</a\s*>',
                text,
                re.I | re.S
            ):
                block = match.group(0)
                opening = re.match(r'<a\b[^>]*>', block, re.I | re.S)

                if not opening:
                    continue

                tag = opening.group(0)
                href = self._absolute(self._attr(tag, "href"), base)

                if (
                    not href
                    or not self._is_detail_url(href)
                    or href in seen
                ):
                    continue

                title = self._clean(self._attr(tag, "title"))

                if not title:
                    title = self._clean(block)

                image = self._image(block, base)

                if not title:
                    continue

                seen.add(href)
                result.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": image,
                    "vod_remarks": ""
                })

        return result

    def _page_url(self, base, page):
        page = max(1, int(page or 1))

        if page <= 1:
            return base

        parsed = urlparse(base)
        path = parsed.path.rstrip("/")

        return (
            parsed.scheme + "://" + parsed.netloc +
            path + "/page/" + str(page) + "/"
        )

    def _hls_url(self, text, page_url):
        # 优先读取站点提供的 embedURL
        embed = self._meta(text, "embedURL")

        # 没有 embedURL 时读取 iframe src
        if not embed:
            iframe = re.search(
                r"<iframe\b[^>]*>",
                text,
                re.I | re.S
            )
            if iframe:
                embed = self._attr(iframe.group(0), "src")

        if not embed:
            embed = page_url

        embed = self._absolute(embed, page_url)

        # 从播放器 UUID 中提取视频 ID
        uuid_pattern = (
            r'([0-9a-f]{8}-[0-9a-f]{4}-'
            r'[0-9a-f]{4}-[0-9a-f]{4}-'
            r'[0-9a-f]{12})'
        )

        match = re.search(uuid_pattern, embed, re.I)

        if not match:
            match = re.search(uuid_pattern, text, re.I)

        if not match:
            return ""

        video_id = match.group(1)

        # 已确认的 HLS 地址格式
        return (
            self.hls_host
            + "/hls/"
            + video_id
            + "/master.jpeg.m3u8"
        )

    def homeContent(self, filter):
        return {
            "class": self.classes,
            "filters": {}
        }

    def homeVideoContent(self):
        text = self._get(self.host + "/")
        return {
            "list": self._cards(text, self.host)
        }

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        if tid == "home":
            base = self.host + "/"
        elif tid.startswith(("http://", "https://")):
            base = tid
        else:
            base = self._absolute(tid)

        url = self._page_url(base, page)
        text = self._get(url)
        videos = self._cards(text, url)

        if not videos and page > 1:
            fallback = base.rstrip("/") + "/?paged=" + str(page)
            text = self._get(fallback)
            videos = self._cards(text, fallback)

        return {
            "list": videos,
            "page": str(page),
            "pagecount": 9999 if videos else page,
            "limit": 30,
            "total": 999999 if videos else len(videos)
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        text = self._get(
            self.host + "/",
            params={
                "s": key,
                "paged": page
            }
        )

        return {
            "list": self._cards(text, self.host),
            "page": str(page),
            "pagecount": 9999,
            "limit": 30,
            "total": 999999
        }

    def detailContent(self, ids):
        result = []

        for vod_id in ids:
            url = self._absolute(unquote(vod_id))
            text = self._get(url)

            if not text:
                continue

            title = (
                self._meta(text, "og:title")
                or self._meta(text, "twitter:title")
            )

            if not title:
                match = re.search(
                    r"<title[^>]*>(.*?)</title>",
                    text,
                    re.I | re.S
                )
                if match:
                    title = self._clean(match.group(1))

            title = self._clean(title) or "视频"

            pic = (
                self._meta(text, "og:image")
                or self._meta(text, "thumbnailUrl")
                or self._meta(text, "twitter:image")
            )

            if pic:
                pic = self._absolute(pic, url)

            desc = (
                self._meta(text, "description")
                or self._meta(text, "og:description")
            )
            desc = self._clean(desc)

            # 从外层详情页取得视频 UUID，并生成 HLS URL
            play_url = self._hls_url(text, url)

            # 仅在识别到 UUID 时输出 HLS 地址
            play_list = "播放$" + play_url if play_url else ""

            vod = {
                "vod_id": url,
                "vod_name": title,
                "vod_pic": pic,
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": desc,
                "vod_play_from": "HLS" if play_list else "",
                "vod_play_url": play_list
            }

            result.append(vod)

        return {
            "list": result
        }

    def playerContent(self, flag, id, vipFlags):
        play_url = unquote(id or "").strip()

        if not play_url.startswith(("http://", "https://")):
            play_url = self._absolute(play_url)

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Referer": self.player_host + "/"
            }
        }

    def isVideoFormat(self, url):
        if not url:
            return False

        lower = url.lower().split("?")[0]

        return lower.endswith((
            ".m3u8",
            ".mp4",
            ".mkv",
            ".flv",
            ".ts",
            ".mpd",
            ".mov",
            ".webm"
        ))

    def manualVideoCheck(self):
        return {
            "time": 0,
            "weight": 0,
            "check": 0
        }