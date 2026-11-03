# coding=utf-8
# 橙果短剧 TVBox 爬虫
# 站点: https://chengguodj.com
# 来源: ForwardWidget 转换

import re
import json
import base64
from urllib.parse import quote, unquote, urljoin
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://chengguodj.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/"
        }

    def getName(self):
        return "橙果短剧"

    def isVideoFormat(self, url):
        return r"\.m3u8|\.mp4" in url

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_id": "yuanchuang", "type_name": "原创短剧"},
            {"type_id": "mogai", "type_name": "魔改短剧"},
            {"type_id": "manju", "type_name": "漫剧"},
            {"type_id": "zhenren", "type_name": "真人短剧"},
            {"type_id": "aiduanju", "type_name": "AI短剧"},
            {"type_id": "browse", "type_name": "片库索引"},
        ]
        result["class"] = classes
        result["list"] = []
        return result

    def homeVideoContent(self):
        return self.categoryContent("yuanchuang", "1", False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        page = int(pg) if pg else 1
        if page <= 1:
            url = f"{self.host}/{tid}"
        else:
            url = f"{self.host}/{tid}/page-{page}"
        html = self.fetch(url, headers=self.headers).text
        videos = self._extract_list(html)
        result["list"] = videos
        result["page"] = page
        result["pagecount"] = 999
        result["limit"] = 20
        result["total"] = 999999
        return result

    def detailContent(self, ids):
        result = {}
        raw = ids[0] if isinstance(ids, list) else ids
        path, list_title, list_pic = self._parse_link(raw)

        detail_url = self._abs_url(path)
        html = self.fetch(detail_url, headers=self.headers).text

        # 标题
        title = list_title or ""
        if not title:
            m = re.search(r"<title>([^<]+)</title>", html, re.I)
            if m:
                title = m.group(1).split("-")[0].replace("在线观看", "").strip()
        if not title:
            title = path

        # 封面
        pic = list_pic or ""
        if self._is_bad_pic(pic):
            wlw = re.search(r'["\'](https?://[^"\']*wlwvch\.cn[^"\']+)["\']', html, re.I)
            if wlw and not self._is_bad_pic(wlw.group(1)):
                pic = wlw.group(1)
        if self._is_bad_pic(pic):
            og = re.search(r'property="og:image"\s+content="([^"]+)"', html, re.I)
            if og and not self._is_bad_pic(og.group(1)):
                pic = og.group(1)
        if self._is_bad_pic(pic):
            arr = self._parse_nuxt(html)
            if arr:
                for v in arr:
                    if isinstance(v, str) and re.search(r"\.(jpg|jpeg|png|webp)", v, re.I) and v.startswith("http") and not self._is_bad_pic(v):
                        pic = v
                        break
        if self._is_bad_pic(pic):
            pic = list_pic or ""

        # 简介
        desc = ""
        dm = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if dm:
            desc = dm.group(1).strip()

        # 集数
        slug = path.rstrip("/").split("/")[-1]
        episodes = []
        arr = self._parse_nuxt(html)
        if arr:
            for item in arr:
                if not isinstance(item, dict):
                    continue
                if "total_episode_count" not in item:
                    continue
                tot = self._nuxt_val(arr, item.get("total_episode_count"))
                if isinstance(tot, int) and tot > 0:
                    for ep in range(1, tot + 1):
                        episodes.append({
                            "name": f"第{ep}集",
                            "path": f"/play/{slug}/{ep}"
                        })
                    break

        if not episodes:
            links = re.findall(r'href=["\'](/play/[^"\']+)["\']', html, re.I)
            seen = set()
            for p in links:
                if p in seen:
                    continue
                seen.add(p)
                num = p.split("/")[-1]
                name = f"第{num}集" if num.isdigit() else num
                episodes.append({"name": name, "path": p})

        if not episodes:
            tot_m = re.search(r"(\d+)\s*(?:集|话)", html)
            max_ep = int(tot_m.group(1)) if tot_m else 1
            if max_ep > 200:
                max_ep = 40
            for e in range(1, max_ep + 1):
                episodes.append({"name": f"第{e}集", "path": f"/play/{slug}/{e}"})

        # 播放列表（用 $$$ 和 # 分隔，TVBox 标准格式）
        play_list = []
        for ep in episodes:
            play_list.append(f"{ep['name']}${ep['path']}")
        play_from = "橙果"
        play_url = "#".join(play_list)

        vod = {
            "vod_id": path,
            "vod_name": title,
            "vod_pic": self._proxy_img(pic) if pic else "",
            "vod_content": desc,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
            "type_name": "短剧",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": f"全{len(episodes)}集" if episodes else ""
        }
        result["list"] = [vod]
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {}
        page = int(pg) if pg else 1
        url = f"{self.host}/search?keyword={quote(key)}"
        if page > 1:
            url += f"&page={page}"
        html = self.fetch(url, headers=self.headers).text
        videos = self._extract_list(html)
        result["list"] = videos
        result["page"] = page
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        path = id
        if path.startswith("http") and ".m3u8" in path:
            result["parse"] = 0
            result["url"] = path
            result["header"] = self.headers
            return result

        play_url = self._resolve_play(path)
        if play_url:
            result["parse"] = 0
            result["url"] = play_url
            result["header"] = self.headers
        else:
            result["parse"] = 1
            result["url"] = self._abs_url(path)
            result["header"] = self.headers
        return result

    # ==================== 内部工具 ====================

    def _abs_url(self, u):
        u = (u or "").strip()
        u = u.replace("\\u002f", "/").replace("\\u002F", "/").replace("\\/", "/").replace("\\", "")
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self.host + u
        return self.host + "/" + u

    def _proxy_img(self, raw):
        """站内封面反代（可选，直接用原图也行）"""
        raw = self._abs_url(raw)
        if not raw:
            return ""
        if raw.startswith(self.host + "/_img/"):
            return raw
        try:
            b64 = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
            return f"{self.host}/_img/{b64}"
        except Exception:
            return raw

    def _is_bad_pic(self, u):
        u = (u or "").strip()
        if not u:
            return True
        return bool(re.search(r"social-default|shared/logo|logo\.png|placeholder|default\.(jpg|png)", u, re.I))

    def _parse_nuxt(self, html):
        m = re.search(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', html, re.I)
        if not m:
            return None
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            return None

    def _nuxt_val(self, arr, idx):
        if isinstance(idx, int) and 0 <= idx < len(arr):
            return arr[idx]
        return idx

    def _extract_list(self, html):
        arr = self._parse_nuxt(html)
        if not arr:
            return []
        items = []
        seen = set()
        for item in arr:
            if not isinstance(item, dict):
                continue
            if "title" not in item:
                continue
            if "slug" not in item and "detail_route" not in item:
                continue

            title = self._nuxt_val(arr, item.get("title"))
            if not title or not isinstance(title, str):
                continue
            title = title.strip()
            if not title:
                continue

            drama_path = self._nuxt_val(arr, item.get("detail_route"))
            if not drama_path or not isinstance(drama_path, str):
                slug = self._nuxt_val(arr, item.get("slug"))
                if slug and isinstance(slug, str):
                    drama_path = f"/drama/{slug}"
            if not drama_path or not isinstance(drama_path, str):
                continue
            drama_path = drama_path.strip()
            if drama_path in seen:
                continue
            seen.add(drama_path)

            pic = ""
            cover_obj = self._nuxt_val(arr, item.get("cover"))
            if isinstance(cover_obj, dict):
                raw_u = self._nuxt_val(arr, cover_obj.get("url"))
                if raw_u and isinstance(raw_u, str):
                    pic = raw_u

            eps = (
                self._nuxt_val(arr, item.get("total_episode_count"))
                or self._nuxt_val(arr, item.get("published_episode_count"))
                or self._nuxt_val(arr, item.get("latest_episode_number"))
            )
            if isinstance(eps, dict):
                eps = ""
            remarks = f"全{eps}集" if eps else ""

            # vod_id 用 path||title||pic 方便详情页带列表封面
            vod_id = f"{drama_path}||{quote(title)}||{quote(pic)}"
            items.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._proxy_img(pic) if pic else "",
                "vod_remarks": remarks
            })
        return items

    def _parse_link(self, link):
        raw = (link or "").strip()
        list_title = ""
        list_pic = ""
        if raw.startswith("cg:"):
            raw = raw[3:]
        if "||" in raw:
            parts = raw.split("||")
            raw = parts[0]
            if len(parts) >= 2:
                try:
                    list_title = unquote(parts[1])
                except Exception:
                    list_title = parts[1]
            if len(parts) >= 3:
                try:
                    list_pic = unquote(parts[2])
                except Exception:
                    list_pic = parts[2]
        return raw, list_title, list_pic

    def _resolve_play(self, play_path):
        url = self._abs_url(play_path)
        html = self.fetch(url, headers=self.headers).text
        arr = self._parse_nuxt(html)
        if arr:
            for v in arr:
                if isinstance(v, str) and ".m3u8" in v and v.startswith("http"):
                    return v.replace("\\u002f", "/").replace("\\u002F", "/").replace("\\/", "/")
        m = re.search(r'["\'](https?://[^"\'\s<>\\]+\.m3u8[^"\'\s<>\\]*)["\']', html, re.I)
        if m:
            return m.group(1).replace("\\u002f", "/").replace("\\u002F", "/").replace("\\/", "/")
        return ""