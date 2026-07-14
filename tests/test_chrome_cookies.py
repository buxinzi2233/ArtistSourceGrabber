# -*- coding: utf-8 -*-
import json
import os
import unittest
from unittest import mock

from sources import chrome_cookies
from sources.chrome_cookies import BrowserCookie, ChromeCookieError


class ChromeCookieTests(unittest.TestCase):
    def test_cookie_representation_never_contains_value(self):
        cookie = BrowserCookie(
            name="auth_token", value="fake-sensitive-value", domain=".x.com")
        self.assertNotIn("fake-sensitive-value", repr(cookie))
        self.assertNotIn("fake-sensitive-value", str(cookie))
        self.assertEqual(cookie.value, "fake-sensitive-value")

    def test_target_filter_only_returns_requested_domain(self):
        raw = [
            {"name": "auth_token", "value": "fake-auth", "domain": ".x.com",
             "path": "/", "secure": True, "httpOnly": True},
            {"name": "ct0", "value": "fake-csrf", "domain": "api.x.com"},
            {"name": "wrong", "value": "fake-wrong", "domain": ".notx.com"},
            {"name": "other", "value": "fake-other", "domain": ".example.com"},
        ]
        cookies = chrome_cookies._target_cookies(raw, ("x.com",))
        self.assertEqual([item.name for item in cookies], ["auth_token", "ct0"])
        self.assertTrue(cookies[0].secure)
        self.assertTrue(cookies[0].http_only)

    @mock.patch.object(chrome_cookies, "_secure_remove_tree", return_value=True)
    @mock.patch.object(chrome_cookies, "_stop_process")
    @mock.patch.object(chrome_cookies, "_read_all_cookies")
    @mock.patch.object(chrome_cookies, "_wait_for_devtools", return_value="ws://127.0.0.1/devtools")
    @mock.patch.object(chrome_cookies, "_launch_chrome")
    @mock.patch.object(chrome_cookies, "_reserve_local_port", return_value=9222)
    @mock.patch.object(chrome_cookies, "_create_snapshot", return_value="X:/Temp/x-chrome-cdp-test")
    @mock.patch.object(chrome_cookies, "_resolve_profile_name", return_value="Profile 7")
    @mock.patch.object(chrome_cookies, "_resolve_browser_paths")
    def test_extract_orchestrates_isolated_chrome_and_cleanup(
            self, resolve_paths, _resolve_profile, create_snapshot, _port,
            launch, _wait, read_all, stop, cleanup):
        resolve_paths.return_value = chrome_cookies._BrowserPaths(
            "C:/Chrome/chrome.exe", "C:/Chrome/User Data")
        process = mock.Mock()
        launch.return_value = process
        read_all.return_value = [
            {"name": "auth_token", "value": "fake-auth", "domain": ".x.com"},
            {"name": "ct0", "value": "fake-csrf", "domain": ".x.com"},
            {"name": "SID", "value": "fake-google", "domain": ".google.com"},
        ]

        result = chrome_cookies.extract_cookies(
            profile="Profile 7", required_names=("auth_token", "ct0"))

        self.assertEqual([item.name for item in result], ["auth_token", "ct0"])
        create_snapshot.assert_called_once_with("C:/Chrome/User Data", "Profile 7")
        launch.assert_called_once_with(
            "C:/Chrome/chrome.exe", "X:/Temp/x-chrome-cdp-test", "Profile 7", 9222)
        stop.assert_called_once_with(process)
        cleanup.assert_called_once_with("X:/Temp/x-chrome-cdp-test")

    @mock.patch.object(chrome_cookies, "_secure_remove_tree", return_value=True)
    @mock.patch.object(chrome_cookies, "_stop_process")
    @mock.patch.object(
        chrome_cookies, "_read_all_cookies",
        side_effect=RuntimeError("fake-sensitive-value"))
    @mock.patch.object(chrome_cookies, "_wait_for_devtools", return_value="ws://127.0.0.1/devtools")
    @mock.patch.object(chrome_cookies, "_launch_chrome")
    @mock.patch.object(chrome_cookies, "_reserve_local_port", return_value=9222)
    @mock.patch.object(chrome_cookies, "_create_snapshot", return_value="X:/Temp/x-chrome-cdp-test")
    @mock.patch.object(chrome_cookies, "_resolve_profile_name", return_value="Profile 7")
    @mock.patch.object(chrome_cookies, "_resolve_browser_paths")
    def test_unexpected_failure_is_redacted_and_still_cleans_up(
            self, resolve_paths, _profile, _snapshot, _port, launch,
            _wait, _read, stop, cleanup):
        resolve_paths.return_value = chrome_cookies._BrowserPaths(
            "C:/Chrome/chrome.exe", "C:/Chrome/User Data")
        process = mock.Mock()
        launch.return_value = process

        with self.assertRaises(ChromeCookieError) as raised:
            chrome_cookies.extract_cookies(profile="Profile 7")

        self.assertEqual(raised.exception.code, "unexpected_error")
        self.assertNotIn("fake-sensitive-value", str(raised.exception))
        stop.assert_called_once_with(process)
        cleanup.assert_called_once_with("X:/Temp/x-chrome-cdp-test")

    @mock.patch.object(chrome_cookies, "_secure_remove_tree", return_value=True)
    @mock.patch.object(chrome_cookies, "_stop_process")
    @mock.patch.object(chrome_cookies, "_read_all_cookies", return_value=[])
    @mock.patch.object(chrome_cookies, "_wait_for_devtools", return_value="ws://127.0.0.1/devtools")
    @mock.patch.object(chrome_cookies, "_launch_chrome")
    @mock.patch.object(chrome_cookies, "_reserve_local_port", return_value=9222)
    @mock.patch.object(chrome_cookies, "_create_snapshot", return_value="X:/Temp/x-chrome-cdp-test")
    @mock.patch.object(chrome_cookies, "_resolve_profile_name", return_value="Profile 7")
    @mock.patch.object(chrome_cookies, "_resolve_browser_paths")
    def test_zero_cookies_reports_app_bound_snapshot_unavailable(
            self, resolve_paths, _profile, _snapshot, _port, launch,
            _wait, _read, stop, cleanup):
        resolve_paths.return_value = chrome_cookies._BrowserPaths(
            "C:/Chrome/chrome.exe", "C:/Chrome/User Data")
        process = mock.Mock()
        launch.return_value = process

        with self.assertRaises(ChromeCookieError) as raised:
            chrome_cookies.extract_cookies(
                profile="Profile 7", required_names=("auth_token", "ct0"))

        self.assertEqual(raised.exception.code, "app_bound_cookie_unavailable")
        self.assertIn("App-Bound Encryption", str(raised.exception))
        stop.assert_called_once_with(process)
        cleanup.assert_called_once_with("X:/Temp/x-chrome-cdp-test")

    @mock.patch.object(chrome_cookies.subprocess, "Popen")
    def test_launch_refuses_original_or_non_temporary_profile(self, popen):
        with self.assertRaises(ChromeCookieError) as raised:
            chrome_cookies._launch_chrome(
                "C:/Chrome/chrome.exe", "C:/Chrome/User Data", "Profile 7", 9222)
        self.assertEqual(raised.exception.code, "unsafe_snapshot")
        popen.assert_not_called()

    def test_cdp_call_ignores_events_and_matches_request_id(self):
        connection = mock.Mock()
        connection.recv.side_effect = [
            json.dumps({"method": "Target.targetInfoChanged", "params": {}}),
            json.dumps({"id": 7, "result": {"ok": True}}),
        ]
        result = chrome_cookies._cdp_call(
            connection, 7, "Target.getTargets", timeout=1.0)
        self.assertEqual(result, {"ok": True})
        sent = json.loads(connection.send.call_args.args[0])
        self.assertEqual(sent["method"], "Target.getTargets")

    def test_cdp_error_does_not_echo_protocol_message(self):
        connection = mock.Mock()
        connection.recv.return_value = json.dumps({
            "id": 1,
            "error": {"code": -1, "message": "fake-sensitive-value"},
        })
        with self.assertRaises(ChromeCookieError) as raised:
            chrome_cookies._cdp_call(
                connection, 1, "Network.getAllCookies", timeout=1.0)
        self.assertNotIn("fake-sensitive-value", str(raised.exception))

    @mock.patch("builtins.open", new_callable=mock.mock_open,
                read_data='{"profile":{"last_used":"Profile 7"}}')
    @mock.patch.object(os.path, "isdir", return_value=True)
    def test_empty_profile_uses_chrome_last_used(self, _isdir, _open):
        self.assertEqual(
            chrome_cookies._resolve_profile_name("C:/Chrome/User Data", ""),
            "Profile 7")

    @mock.patch.object(chrome_cookies, "_secure_remove_tree", return_value=True)
    @mock.patch.object(chrome_cookies.shutil, "copy2")
    @mock.patch.object(chrome_cookies.os, "makedirs")
    @mock.patch.object(chrome_cookies.os, "chmod")
    @mock.patch.object(chrome_cookies.tempfile, "mkdtemp",
                       return_value="X:/Temp/x-chrome-cdp-test")
    def test_snapshot_copies_only_minimal_profile_files(
            self, _mkdtemp, _chmod, _makedirs, copy2, _cleanup):
        root = "C:/Chrome/User Data"
        profile = "Profile 7"
        existing = {
            os.path.join(root, "Local State"),
            os.path.join(root, profile, "Preferences"),
            os.path.join(root, profile, "Secure Preferences"),
            os.path.join(root, profile, "Network", "Network Persistent State"),
            os.path.join(root, profile, "Network", "Cookies"),
            os.path.join(root, profile, "Network", "Cookies-wal"),
        }
        with mock.patch.object(chrome_cookies.os.path, "isfile",
                               side_effect=lambda path: path in existing):
            result = chrome_cookies._create_snapshot(root, profile)

        self.assertEqual(result, "X:/Temp/x-chrome-cdp-test")
        copied_sources = {call.args[0] for call in copy2.call_args_list}
        self.assertEqual(copied_sources, existing)


if __name__ == "__main__":
    unittest.main()
