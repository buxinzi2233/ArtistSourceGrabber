import os
import unittest
from unittest import mock

import app


class ManagedPixivSessionUiTests(unittest.TestCase):
    def test_open_and_check_whitelist_session_response(self):
        module = mock.Mock()
        module.open_login_window.return_value = {
            "ok": True, "running": True, "logged_in": False,
            "message": "opened", "profile_dir": "must-not-leak", "pid": 123,
        }
        module.check_login.return_value = {
            "ok": True, "running": True, "logged_in": True,
            "message": "登录已保存，后台运行", "phpsessid": "must-not-leak",
        }
        with mock.patch.object(app, "_pixiv_browser_session_module", return_value=module):
            opened = app.open_pixiv_browser_session()
            checked = app.check_pixiv_browser_session()

        module.open_login_window.assert_called_once_with()
        self.assertNotIn("profile_dir", opened)
        self.assertNotIn("pid", opened)
        self.assertNotIn("phpsessid", checked)
        self.assertTrue(checked["logged_in"])

    def test_frontend_defaults_to_managed_and_folds_legacy_credentials(self):
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "static", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        with open(os.path.join(root, "static", "app.js"), encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn('id="pixivCookieMode"', html)
        self.assertIn('id="pixivLegacySettings"', html)
        self.assertIn("/api/pixiv/session/open", script)
        self.assertIn("/api/pixiv/session/check", script)
        self.assertIn('els.pixivLegacySettings.open=!managed', script)
        self.assertIn('pixiv_cookie_mode', script)


if __name__ == "__main__":
    unittest.main()
