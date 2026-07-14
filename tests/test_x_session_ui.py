import os
import unittest
from unittest import mock

import app


class ManagedXSessionUiTests(unittest.TestCase):
    def test_open_uses_target_artist_and_whitelists_response(self):
        module = mock.Mock()
        module.open_login_window.return_value = {
            "ok": True,
            "running": True,
            "logged_in": False,
            "message": "opened",
            "auth_token": "must-not-leak",
            "cookie_path": "must-not-leak",
        }
        with mock.patch.object(app, "_x_browser_session_module", return_value=module):
            result = app.open_x_browser_session("@kantoku_5th")

        module.open_login_window.assert_called_once_with(
            url="https://x.com/kantoku_5th/media")
        self.assertEqual(result, {
            "ok": True, "running": True, "logged_in": False,
            "message": "opened",
        })

    def test_check_whitelists_response(self):
        module = mock.Mock()
        module.check_login.return_value = {
            "ok": True, "running": True, "logged_in": True,
            "message": "logged in", "cookies": ["secret"],
        }
        with mock.patch.object(app, "_x_browser_session_module", return_value=module):
            result = app.check_x_browser_session()
        self.assertTrue(result["logged_in"])
        self.assertNotIn("cookies", result)

    def test_frontend_exposes_managed_mode_without_persisting_secrets(self):
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "static", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        with open(os.path.join(root, "static", "app.js"), encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn('value="managed"', html)
        self.assertIn("/api/x/session/open", script)
        self.assertIn("/api/x/session/check", script)
        self.assertIn("x_cookie_mode", script)
        self.assertIn('id="xLegacySettings"', html)
        self.assertIn("兼容模式设置", html)
        self.assertIn("els.xLegacySettings.open=!managed", script)
        self.assertIn('els.xLegacySettings.classList.toggle("hidden",!isTwitter)', script)
        save_block = script[script.index("function saveSettings"):
                            script.index("function loadSettings")]
        self.assertNotIn("auth_token", save_block)
        self.assertNotIn("ct0", save_block)
        self.assertNotIn("llmApiKey", save_block)


if __name__ == "__main__":
    unittest.main()
