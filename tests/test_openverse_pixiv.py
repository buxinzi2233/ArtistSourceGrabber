# -*- coding: utf-8 -*-
import unittest
from unittest import mock

from sources.openverse import OpenverseSource
from sources.pixiv import PixivSource


def source_cfg(source, **overrides):
    body = {
        "artist": "11", "count": 0, "rating": "", "tag_format": "comma",
        "include_artist": True, "include_meta": True,
        "openverse_license": "all",
    }
    body.update(overrides)
    cfg = source.normalize_cfg(body)
    if isinstance(cfg, str):
        raise AssertionError(cfg)
    return cfg


class OpenverseSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = OpenverseSource()
        self.cfg = source_cfg(self.source, artist="Example Artist")

    def test_search_marks_aggregated_creator_as_low_confidence(self):
        payload = {"result_count": 2, "results": [
            {"id": "a", "creator": "Same Name", "creator_url": "https://example.test/a"},
            {"id": "b", "creator": "same name", "foreign_landing_url": "https://example.test/b"},
        ]}
        with mock.patch.object(self.source, "_api", return_value=payload):
            results = self.source.search_artists("same", self.cfg)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["post_count"], 2)
        self.assertEqual(results[0]["match_confidence"], "low")
        self.assertIn("低置信度", results[0]["other_names"])

    def test_search_does_not_turn_network_failure_into_empty_results(self):
        with mock.patch.object(self.source, "_api", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                self.source.search_artists("same", self.cfg)

    def test_count_and_list_return_downloadable_post(self):
        count_page = {"result_count": 7, "results": []}
        list_page = {"result_count": 7, "results": [{
            "id": "image-1", "creator": "Example Artist",
            "url": "https://images.example.test/original.png",
            "thumbnail": "https://images.example.test/thumb.jpg",
            "filetype": "png", "foreign_landing_url": "https://example.test/work/1",
            "tags": [{"name": "digital_art"}], "license": "cc0",
        }]}
        with mock.patch.object(self.source, "_api", side_effect=[count_page, list_page]):
            self.assertEqual(self.source.count_posts("Example Artist", self.cfg), 7)
            post = self.source.list_posts("Example Artist", 1, self.cfg)[0]
        self.assertEqual(post["file_url"], "https://images.example.test/original.png")
        self.assertEqual(post["ext"], "png")
        self.assertEqual(self.source.make_filename(post, self.cfg), "openverse_image-1.png")

    def test_api_error_and_malformed_count_raise(self):
        with mock.patch("sources.openverse.http_request", return_value={"detail": "rate limited"}):
            with self.assertRaisesRegex(RuntimeError, "rate limited"):
                self.source._api({"q": "x"}, self.cfg)
        with mock.patch.object(self.source, "_api", return_value={"results": [], "result_count": None}):
            with self.assertRaisesRegex(RuntimeError, "作品总数"):
                self.source.count_posts("x", self.cfg)

    def test_nonempty_page_without_download_url_is_an_error(self):
        with mock.patch.object(self.source, "_api", return_value={
                "result_count": 1, "results": [{"id": "broken", "creator": "x"}]}):
            with self.assertRaisesRegex(RuntimeError, "可下载"):
                self.source.list_posts("x", 1, self.cfg)


class PixivSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = PixivSource()

    def test_phpsessid_is_only_a_web_cookie(self):
        cfg = source_cfg(self.source, phpsessid="session-value", access_token="")
        web_headers = self.source.auth_headers(cfg)
        self.assertEqual(web_headers["Cookie"], "PHPSESSID=session-value")
        self.assertNotIn("Authorization", web_headers)
        with self.assertRaisesRegex(RuntimeError, "access_token"):
            self.source._app_headers(cfg)

    def test_access_token_is_bearer_and_never_cookie(self):
        cfg = source_cfg(self.source, access_token="token-value", phpsessid="session-value")
        headers = self.source.auth_headers(cfg)
        self.assertEqual(headers["Authorization"], "Bearer token-value")
        self.assertNotIn("Cookie", headers)

    def test_managed_cookie_is_read_live_for_each_web_request(self):
        cfg = source_cfg(
            self.source, pixiv_cookie_mode="managed",
            phpsessid="ignored-manual-value", access_token="")
        with mock.patch(
                "sources.pixiv_browser_session.read_phpsessid",
                side_effect=["live-one", "live-two"]) as read:
            first = self.source.auth_headers(cfg)
            second = self.source.auth_headers(cfg)
        self.assertEqual(first["Cookie"], "PHPSESSID=live-one")
        self.assertEqual(second["Cookie"], "PHPSESSID=live-two")
        self.assertEqual(read.call_count, 2)
        self.assertNotIn("ignored-manual-value", repr((first, second)))

    def test_invalid_managed_cookie_mode_is_rejected(self):
        body = {
            "artist": "11", "count": 0, "rating": "",
            "tag_format": "comma", "pixiv_cookie_mode": "unknown",
        }
        self.assertIn("Cookie 登录模式", self.source.normalize_cfg(body))

    def test_app_api_error_is_not_silent(self):
        cfg = source_cfg(self.source, access_token="token")
        response = {"error": {"user_message": "invalid token"}}
        with mock.patch("sources.pixiv.http_request", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "invalid token"):
                self.source._app_api("/v1/user/illusts", {}, cfg)

    def test_username_search_error_is_not_an_empty_list(self):
        cfg = source_cfg(self.source, artist="name", access_token="token")
        with mock.patch.object(self.source, "_search_users_app", side_effect=RuntimeError("API down")):
            with self.assertRaisesRegex(RuntimeError, "API down"):
                self.source.search_artists("name", cfg)

    def test_web_mode_requires_numeric_id_for_name_resolution(self):
        cfg = source_cfg(self.source, artist="not-a-number")
        with self.assertRaisesRegex(RuntimeError, "数字用户 ID"):
            self.source.resolve_artist(cfg, lambda _message: None)
        cfg["artist"] = "https://www.pixiv.net/en/users/12345/artworks"
        self.assertEqual(self.source.resolve_artist(cfg, lambda _message: None), "12345")

    def test_web_connection_test_rejects_a_username_it_cannot_resolve(self):
        cfg = source_cfg(self.source, artist="name-without-token")
        ok, message = self.source.test(cfg)
        self.assertFalse(ok)
        self.assertIn("数字用户 ID", message)

    def test_app_listing_expands_manga_and_marks_ugoira_for_skip(self):
        cfg = source_cfg(self.source, access_token="token")
        response = {"illusts": [
            {
                "id": 100, "type": "manga", "x_restrict": 0,
                "user": {"id": 9, "name": "Artist", "account": "artist"},
                "tags": [{"name": "tag_a"}],
                "meta_pages": [
                    {"image_urls": {"original": "https://i.pximg.net/100_p0.png"}},
                    {"image_urls": {"original": "https://i.pximg.net/100_p1.jpg"}},
                ],
            },
            {
                "id": 101, "type": "ugoira", "x_restrict": 0,
                "user": {"id": 9, "name": "Artist"}, "meta_pages": [],
            },
        ]}
        with mock.patch.object(self.source, "_app_api", return_value=response) as api:
            posts = self.source.list_posts("9", 1, cfg)
        self.assertEqual([post["id"] for post in posts], ["100_p0", "100_p1", "101"])
        self.assertEqual([post["ext"] for post in posts[:2]], ["png", "jpg"])
        self.assertTrue(self.source.skip_post(posts[2], cfg))
        params = api.call_args.args[1]
        self.assertNotIn("type", params)

    def test_web_listing_uses_stable_pagination_and_expands_pages(self):
        cfg = source_cfg(self.source, count=1, phpsessid="session")
        work = {
            "id": "300", "illustType": 1, "xRestrict": 0,
            "userId": "7", "userName": "Artist", "tags": ["tag one"],
        }
        with mock.patch.object(self.source, "_web_profile_ids", return_value=["300", "200"]), \
                mock.patch.object(self.source, "_web_work_batch", return_value={"300": work}) as batch, \
                mock.patch.object(self.source, "_web_api", return_value=[
                    {"urls": {"original": "https://i.pximg.net/300_p0.jpg"}},
                    {"urls": {"original": "https://i.pximg.net/300_p1.png"}},
                ]):
            posts = self.source.list_posts("7", 1, cfg)
        self.assertEqual([post["id"] for post in posts], ["300_p0", "300_p1"])
        self.assertEqual(batch.call_args.args[1], ["300"])
        self.assertEqual(self.source.make_filename(posts[1], cfg), "pixiv_7_300_p1.png")

    def test_web_api_error_is_not_silent(self):
        cfg = source_cfg(self.source, phpsessid="session")
        with mock.patch("sources.pixiv.http_request", return_value={"error": True, "message": "login required"}):
            with self.assertRaisesRegex(RuntimeError, "login required"):
                self.source._web_api("/user/1/profile/all", None, cfg)


if __name__ == "__main__":
    unittest.main()
