# -*- coding: utf-8 -*-
import unittest
from unittest import mock

from sources.twitter import GalleryDLError, TwitterXSource


class TwitterSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = TwitterXSource()
        self.cfg = {
            "auth_token": "token", "ct0": "csrf", "artist": "kantoku_5th",
            "count": 1, "x_mode": "media_user", "rating": "",
            "tag_format": "comma", "include_artist": True,
            "include_meta": False, "skip_video": True, "proxy": "",
            "x_cookie_mode": "", "x_cookies_file": "",
            "x_cookies_from_browser": "", "x_browser_profile": "",
        }

    def test_accepts_cookie_header_and_named_values(self):
        cfg = self.source.normalize_cfg({
            "auth_token": "auth_token=abc; ct0=xyz",
            "ct0": "ct0=xyz", "artist": "@kantoku_5th", "count": 1,
        })
        self.assertEqual(cfg["auth_token"], "abc")
        self.assertEqual(cfg["ct0"], "xyz")

    def test_test_uses_authenticated_media_timeline(self):
        profile = [[2, {"rest_id": "99", "core": {"screen_name": "kantoku_5th"},
                        "legacy": {"media_count": 1}}]]
        with mock.patch.object(self.source, "_run_gallery_dl", side_effect=[profile, []]):
            ok, message = self.source.test(self.cfg)
        self.assertTrue(ok)
        self.assertIn("媒体访问", message)

    def test_numeric_x_urls_are_normalized(self):
        self.assertEqual(self.source._normalize_artist(
            "https://x.com/i/user/776240313467756544"), "id:776240313467756544")
        self.assertEqual(self.source._normalize_artist(
            "https://twitter.com/intent/user?user_id=776240313467756544"),
            "id:776240313467756544")

    def test_gallery_auth_error_is_not_hidden_by_graphql(self):
        with mock.patch.object(
                self.source, "_run_gallery_dl",
                side_effect=GalleryDLError("gallery-dl: Could not authenticate you")), \
             mock.patch.object(self.source, "_list_posts_graphql") as fallback:
            with self.assertRaisesRegex(RuntimeError, "401"):
                self.source.list_posts("kantoku_5th", 1, self.cfg)
        fallback.assert_not_called()

    def test_browser_cookie_argument(self):
        cfg = dict(self.cfg, auth_token="", ct0="", x_cookies_from_browser="edge")
        with self.source._cookie_args(cfg) as args:
            self.assertEqual(args, ["--cookies-from-browser", "edge/x.com"])

    def test_managed_browser_mode_does_not_require_manual_cookie(self):
        cfg = self.source.normalize_cfg({
            "artist": "kantoku_5th", "count": 1, "x_cookie_mode": "managed",
        })
        self.assertIsInstance(cfg, dict)
        self.assertEqual(cfg["x_cookie_mode"], "managed")
        self.assertFalse(cfg["auth_token"])

    def test_managed_browser_cookie_file_is_scoped_to_gallery_call(self):
        cfg = dict(
            self.cfg, auth_token="", ct0="", x_cookie_mode="managed")
        with mock.patch(
                "sources.x_browser_session.cookie_file") as managed_cookie_file:
            managed_cookie_file.return_value.__enter__.return_value = "managed.txt"
            with self.source._cookie_args(cfg) as args:
                self.assertEqual(args, ["--cookies", "managed.txt"])
            managed_cookie_file.return_value.__exit__.assert_called_once()

    def test_zero_browser_cookies_has_actionable_error(self):
        message = self.source._friendly_gallery_error(
            GalleryDLError("AuthRequired; Extracted 0 cookies from Chrome"))
        self.assertIn("没有找到 x.com Cookie", message)

    def test_raw_gallery_metadata_without_user_is_supported(self):
        messages = [[3, "https://pbs.twimg.com/media/abc.jpg", {
            "rest_id": "12345",
            "legacy": {
                "id_str": "12345", "full_text": "hello",
                "created_at": "today", "entities": {"hashtags": [{"text": "art"}]},
            },
            "extension": "jpg", "num": 1,
        }]]
        posts = self.source._posts_from_gallery(messages, self.cfg)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["id"], "12345_0")
        self.assertEqual(posts[0]["artist"], "kantoku_5th")
        self.assertEqual(posts[0]["raw"]["hashtags"], ["art"])

    def test_raw_profile_metadata_is_flattened(self):
        profile = self.source._profile_from_gallery([[2, {
            "id": "opaque", "rest_id": "99",
            "core": {"screen_name": "artist", "name": "Artist"},
            "legacy": {"media_count": 12},
        }]])
        self.assertEqual(profile["id"], "99")
        self.assertEqual(profile["name"], "artist")


if __name__ == "__main__":
    unittest.main()
