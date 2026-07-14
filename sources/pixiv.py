# -*- coding: utf-8 -*-
"""Pixiv source using either a real App-API token or Pixiv web AJAX.

``access_token`` is sent only as an App API Bearer token.  ``PHPSESSID`` is a
website session cookie and is therefore sent only to ``www.pixiv.net/ajax``;
it must never be presented to ``app-api.pixiv.net`` as if it were OAuth.

The public web AJAX fallback is intentionally supported without credentials
for public works.  A PHPSESSID may widen the set of works visible to the
logged-in account, while a real access token enables username search and the
more efficient App API listing.
"""
import os
import re
import urllib.parse

from .base import Source, Post
from http_util import http_request, describe_error


API_HOST = "https://app-api.pixiv.net"
WEB_HOST = "https://www.pixiv.net"
REFERER = "https://www.pixiv.net/"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")


class PixivSource(Source):
    id = "pixiv"
    label = "Pixiv"
    api_base = API_HOST
    needs_auth = False
    supports_artist_search = True
    can_count = False

    RATING_VALUES = ("", "all", "safe", "r18")
    WORKS_PER_PAGE = 30
    WEB_WORKS_PER_PAGE = 12
    MAX_TAGS = 50

    def normalize_cfg(self, body):
        artist = str(body.get("artist") or "").strip()
        if not artist:
            return "请填写 Pixiv 画师 ID、用户名或用户主页 URL"
        try:
            count = int(body.get("count") or 0)
        except (TypeError, ValueError):
            return "下载数量必须是整数"
        if count < 0:
            return "下载数量不能为负数"
        rating = str(body.get("rating") or "").strip()
        if rating not in self.RATING_VALUES:
            return "分级参数不合法"
        tag_format = body.get("tag_format")
        if tag_format not in ("comma", "space"):
            tag_format = "comma"
        cookie_mode = str(body.get("pixiv_cookie_mode") or "").strip().lower()
        if cookie_mode not in ("", "legacy", "managed"):
            return "Pixiv Cookie 登录模式不合法"
        return {
            "phpsessid": str(body.get("phpsessid") or "").strip(),
            "pixiv_cookie_mode": cookie_mode,
            "user_id": str(body.get("user_id") or "").strip(),
            "access_token": str(body.get("access_token") or "").strip(),
            "artist": artist,
            "count": count,
            "rating": rating,
            "tag_format": tag_format,
            "include_artist": bool(body.get("include_artist")),
            "include_meta": bool(body.get("include_meta")),
            "skip_video": True,
            "proxy": str(body.get("proxy") or "").strip(),
            # Ugoira needs a separate metadata/zip flow.  This adapter returns
            # a visible skip marker rather than inventing an image/zip URL.
            "include_ugoira": False,
        }

    @staticmethod
    def _extract_user_id(value):
        raw = str(value or "").strip()
        if re.fullmatch(r"\d+", raw):
            return raw
        match = re.search(r"(?:pixiv\.net)/(?:[a-z]{2}/)?users/(\d+)", raw, re.I)
        return match.group(1) if match else ""

    @staticmethod
    def _api_error_message(data):
        if not isinstance(data, dict):
            return "API 返回了无法识别的数据"
        error = data.get("error")
        if not error:
            return ""
        if isinstance(error, dict):
            return str(error.get("user_message") or error.get("message") or
                       error.get("reason") or error)
        return str(data.get("message") or error)

    def _app_headers(self, cfg):
        token = cfg.get("access_token")
        if not token:
            raise RuntimeError("Pixiv App API 需要有效的 access_token")
        return {
            "User-Agent": "PixivIOSApp/7.19.1 (iOS 16.7.2; iPhone12,8)",
            "Referer": "https://app-api.pixiv.net/",
            "Accept-Language": "ja",
            "App-OS": "ios", "App-OS-Version": "16.7.2",
            "App-Version": "7.19.1",
            "Authorization": "Bearer %s" % token,
        }

    def _web_headers(self, cfg, referer=REFERER):
        headers = {"User-Agent": WEB_UA, "Referer": referer, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"}
        phpsessid = cfg.get("phpsessid")
        if cfg.get("pixiv_cookie_mode") == "managed":
            # Read from the live dedicated browser for every web request.  Do
            # not copy the credential into cfg, logs, state, or exception text.
            from .pixiv_browser_session import read_phpsessid
            phpsessid = read_phpsessid()
        if phpsessid:
            headers["Cookie"] = "PHPSESSID=%s" % phpsessid
        return headers

    def auth_headers(self, cfg):
        """Backward-compatible helper with correct authentication semantics."""
        return self._app_headers(cfg) if cfg.get("access_token") else self._web_headers(cfg)

    def _app_api(self, path, params, cfg):
        url = API_HOST + path + "?" + urllib.parse.urlencode(params or {})
        data = http_request(url, cfg.get("proxy"), headers=self._app_headers(cfg), timeout=45)
        message = self._api_error_message(data)
        if message:
            raise RuntimeError("Pixiv App API 返回错误：%s" % message)
        if not isinstance(data, dict):
            raise RuntimeError("Pixiv App API 返回了无法识别的数据")
        return data

    def _web_api(self, path, params, cfg, referer=REFERER):
        query = ("?" + urllib.parse.urlencode(params or {}, doseq=True)) if params else ""
        url = WEB_HOST + "/ajax" + path + query
        data = http_request(url, cfg.get("proxy"), headers=self._web_headers(cfg, referer), timeout=45)
        if not isinstance(data, dict):
            raise RuntimeError("Pixiv 网页 API 返回了无法识别的数据")
        if data.get("error"):
            raise RuntimeError("Pixiv 网页 API 返回错误：%s" % (data.get("message") or "未知错误"))
        if "body" not in data:
            raise RuntimeError("Pixiv 网页 API 返回了无法识别的结果")
        return data["body"]

    def test(self, cfg):
        try:
            if cfg.get("access_token"):
                data = self._app_api("/v1/illust/ranking", {"mode": "day", "filter": "for_ios"}, cfg)
                if not isinstance(data.get("illusts"), list):
                    raise RuntimeError("Pixiv App API 未返回作品列表")
                return True, "Pixiv App API access_token 连接正常"
            uid = self._extract_user_id(cfg.get("artist"))
            if not uid:
                raise RuntimeError("Pixiv 网页模式请填写数字用户 ID 或用户主页 URL")
            body = self._web_api("/user/%s/profile/all" % uid, None, cfg,
                                 "%susers/%s/artworks" % (REFERER, uid))
            if not isinstance(body, dict):
                raise RuntimeError("Pixiv 网页 API 未返回用户作品索引")
            if cfg.get("pixiv_cookie_mode") == "managed":
                mode = "（使用专用浏览器登录会话）"
            else:
                mode = "（使用 PHPSESSID 网页 Cookie）" if cfg.get("phpsessid") else "（公开作品模式）"
            return True, "Pixiv 网页 API 连接正常%s" % mode
        except Exception as exc:
            return False, describe_error(exc)

    def _search_users_app(self, query, cfg):
        data = self._app_api("/v1/search/user", {"word": query, "filter": "for_ios"}, cfg)
        users = data.get("user_previews")
        if not isinstance(users, list):
            raise RuntimeError("Pixiv App API 未返回有效的用户搜索结果")
        return users

    def resolve_artist(self, cfg, logger):
        raw = cfg["artist"].strip()
        uid = self._extract_user_id(raw)
        if uid:
            return uid
        if not cfg.get("access_token"):
            raise RuntimeError("Pixiv 网页模式无法按用户名搜索，请填写数字用户 ID / 主页 URL，或提供 access_token")
        users = self._search_users_app(raw, cfg)
        if not users:
            raise RuntimeError("Pixiv 上找不到用户「%s」" % raw)
        first = users[0]
        user = first.get("user") or {}
        uid = user.get("id")
        if not uid:
            raise RuntimeError("无法解析 Pixiv 用户 ID")
        logger("Pixiv 用户：「%s」 id=%s" % (user.get("name", ""), uid))
        return str(uid)

    def search_artists(self, query, cfg, limit=10):
        if not query:
            return []
        direct_uid = self._extract_user_id(query)
        if direct_uid and not cfg.get("access_token"):
            user = self._web_api("/user/%s" % direct_uid, {"full": 1, "lang": "zh"}, cfg,
                                 "%susers/%s" % (REFERER, direct_uid))
            return [{
                "id": direct_uid,
                "name": str((user or {}).get("name") or direct_uid),
                "site": self.id,
                "profile_url": "%susers/%s" % (REFERER, direct_uid),
                "post_count": None,
                "other_names": "",
                "is_banned": False,
            }]
        if not cfg.get("access_token"):
            raise RuntimeError("Pixiv 用户名搜索需要有效的 access_token；网页模式请粘贴数字用户 ID 或主页 URL")
        out = []
        for preview in self._search_users_app(query, cfg)[:limit]:
            user = preview.get("user") or {}
            uid = user.get("id")
            if not uid:
                continue
            out.append({
                "id": str(uid),
                "name": user.get("name", ""),
                "site": self.id,
                "profile_url": "%susers/%s" % (REFERER, uid),
                "post_count": None,
                "other_names": user.get("account", ""),
                "is_banned": False,
            })
        return out

    def count_posts(self, artist_key, cfg):
        # One Pixiv work may contain many pages.  Reporting a work count as a
        # downloadable-file count would truncate multi-page manga.
        return -1

    @staticmethod
    def _valid_items(data, key, label):
        items = data.get(key)
        if not isinstance(items, list):
            raise RuntimeError("Pixiv %s未返回有效列表" % label)
        if any(not isinstance(item, dict) for item in items):
            raise RuntimeError("Pixiv %s返回了损坏的数据" % label)
        return items

    def _rating_allowed(self, item, cfg):
        rating = cfg.get("rating")
        restricted = int(item.get("x_restrict") if "x_restrict" in item else item.get("xRestrict") or 0)
        if rating == "safe":
            return restricted == 0
        if rating == "r18":
            return restricted > 0
        return True

    @staticmethod
    def _https(url):
        return "https://" + url[7:] if isinstance(url, str) and url.startswith("http://") else url

    @staticmethod
    def _extension(url):
        ext = os.path.splitext(urllib.parse.urlparse(url or "").path)[1].lstrip(".").lower()
        return ext if ext in ("jpg", "jpeg", "png", "gif", "webp") else "jpg"

    def _post(self, work, url, page_index, page_count, work_type):
        work_id = str(work.get("id") or work.get("illustId") or "")
        raw = dict(work)
        raw["_page_index"] = page_index
        raw["_page_count"] = page_count
        raw["_work_id"] = work_id
        raw["type"] = work_type
        user = work.get("user") or {}
        artist = user.get("name") or work.get("userName") or ""
        post_id = "%s_p%d" % (work_id, page_index) if page_count > 1 else work_id
        return Post(
            id=post_id,
            ext=self._extension(url),
            file_url=self._https(url),
            large_url=None,
            is_video=False,
            artist=str(artist),
            raw=raw,
            page_url="%sartworks/%s" % (REFERER, work_id),
            extra_headers={"Referer": REFERER},
        )

    def _normalize_app_work(self, work, cfg):
        if not work.get("id"):
            raise RuntimeError("Pixiv App API 返回了缺少 ID 的作品")
        if not self._rating_allowed(work, cfg):
            return []
        work_type = str(work.get("type") or "illust").lower()
        if work_type == "ugoira":
            return [Post(
                id=str(work["id"]), ext="zip", file_url=None, large_url=None,
                is_video=True, artist=str((work.get("user") or {}).get("name") or ""),
                raw=dict(work), page_url="%sartworks/%s" % (REFERER, work["id"]),
            )]
        pages = work.get("meta_pages") or []
        if pages:
            if not isinstance(pages, list):
                raise RuntimeError("Pixiv 作品 %s 的分页数据损坏" % work["id"])
            urls = []
            for page in pages:
                page_urls = (page or {}).get("image_urls") or {}
                url = page_urls.get("original") or page_urls.get("large")
                if not url:
                    raise RuntimeError("Pixiv 作品 %s 缺少第 %d 页图片 URL" % (work["id"], len(urls) + 1))
                urls.append(url)
        else:
            single = work.get("meta_single_page") or {}
            image_urls = work.get("image_urls") or {}
            url = single.get("original_image_url") or image_urls.get("large") or image_urls.get("medium")
            if not url:
                raise RuntimeError("Pixiv 作品 %s 缺少图片 URL" % work["id"])
            urls = [url]
        return [self._post(work, url, index, len(urls), work_type)
                for index, url in enumerate(urls)]

    def _web_profile_ids(self, artist_key, cfg):
        body = self._web_api("/user/%s/profile/all" % artist_key, None, cfg,
                             "%susers/%s/artworks" % (REFERER, artist_key))
        if not isinstance(body, dict):
            raise RuntimeError("Pixiv 网页 API 未返回有效的作品索引")
        ids = []
        for key in ("illusts", "manga"):
            values = body.get(key) or {}
            if not isinstance(values, dict):
                raise RuntimeError("Pixiv 网页 API 返回了损坏的%s索引" % key)
            ids.extend(str(value) for value in values if str(value).isdigit())
        return sorted(set(ids), key=int, reverse=True)

    def _web_work_batch(self, artist_key, ids, cfg):
        body = self._web_api(
            "/user/%s/profile/illusts" % artist_key,
            [("ids[]", value) for value in ids] + [
                ("work_category", "illustManga"), ("is_first_page", "0"), ("lang", "zh")],
            cfg, "%susers/%s/artworks" % (REFERER, artist_key),
        )
        works = (body or {}).get("works") if isinstance(body, dict) else None
        if not isinstance(works, dict):
            raise RuntimeError("Pixiv 网页 API 未返回有效的作品详情")
        return works

    def _normalize_web_work(self, work, cfg):
        work_id = str(work.get("id") or work.get("illustId") or "")
        if not work_id:
            raise RuntimeError("Pixiv 网页 API 返回了缺少 ID 的作品")
        if not self._rating_allowed(work, cfg):
            return []
        try:
            illust_type = int(work.get("illustType") or 0)
        except (TypeError, ValueError):
            illust_type = 0
        if illust_type == 2:
            raw = dict(work)
            raw["type"] = "ugoira"
            return [Post(
                id=work_id, ext="zip", file_url=None, large_url=None,
                is_video=True, artist=str(work.get("userName") or ""), raw=raw,
                page_url="%sartworks/%s" % (REFERER, work_id),
            )]
        pages = self._web_api("/illust/%s/pages" % work_id, None, cfg,
                              "%sartworks/%s" % (REFERER, work_id))
        if not isinstance(pages, list):
            raise RuntimeError("Pixiv 作品 %s 的分页数据损坏" % work_id)
        urls = []
        for page in pages:
            page_urls = (page or {}).get("urls") or {}
            url = page_urls.get("original") or page_urls.get("regular")
            if not url:
                raise RuntimeError("Pixiv 作品 %s 缺少第 %d 页图片 URL" % (work_id, len(urls) + 1))
            urls.append(url)
        if not urls:
            raise RuntimeError("Pixiv 作品 %s 没有可下载图片" % work_id)
        work_type = "manga" if illust_type == 1 else "illust"
        return [self._post(work, url, index, len(urls), work_type)
                for index, url in enumerate(urls)]

    def list_posts(self, artist_key, page, cfg):
        if page < 1:
            raise ValueError("Pixiv 页码必须从 1 开始")
        if cfg.get("access_token"):
            params = {
                "user_id": int(artist_key), "filter": "for_ios",
                "offset": (page - 1) * self.WORKS_PER_PAGE,
            }
            data = self._app_api("/v1/user/illusts", params, cfg)
            out = []
            for work in self._valid_items(data, "illusts", "作品列表"):
                out.extend(self._normalize_app_work(work, cfg))
            return out

        ids = self._web_profile_ids(artist_key, cfg)
        page_size = self.WEB_WORKS_PER_PAGE
        if cfg.get("count", 0) > 0:
            page_size = min(page_size, max(1, int(cfg["count"])))
        selected = ids[(page - 1) * page_size:page * page_size]
        if not selected:
            return []
        works = self._web_work_batch(artist_key, selected, cfg)
        out = []
        for work_id in selected:
            work = works.get(work_id)
            if not isinstance(work, dict):
                raise RuntimeError("Pixiv 网页 API 缺少作品 %s 的详情" % work_id)
            out.extend(self._normalize_web_work(work, cfg))
        return out

    def skip_post(self, post, cfg):
        if post.get("is_video") or str((post.get("raw") or {}).get("type") or "").lower() == "ugoira":
            return True
        return super().skip_post(post, cfg)

    def make_filename(self, post, cfg):
        raw = post.get("raw") or {}
        user = raw.get("user") or {}
        uid = user.get("id") or raw.get("userId") or "x"
        return "pixiv_%s_%s.%s" % (uid, post.get("id"), post.get("ext") or "jpg")

    def build_caption(self, post, cfg):
        work = post.get("raw") or {}
        tags_raw = work.get("tags") or []
        names = []
        for tag in tags_raw:
            if isinstance(tag, dict):
                name = tag.get("translated_name") or tag.get("name") or ""
            else:
                name = str(tag or "")
            if name:
                names.append(name.replace(" ", "_"))
        if cfg.get("include_artist"):
            user = work.get("user") or {}
            account = user.get("account") or work.get("userAccount") or work.get("userName")
            if account:
                names.insert(0, str(account).replace(" ", "_"))
        if cfg.get("include_meta"):
            work_type = work.get("type")
            if work_type:
                names.append("pixiv_%s" % work_type)
        out_tags = names[:self.MAX_TAGS]
        if cfg.get("tag_format") == "comma":
            pretty = [tag.replace("_", " ").replace("(", "\\(").replace(")", "\\)")
                      for tag in out_tags]
            return ", ".join(pretty)
        return " ".join(out_tags)
