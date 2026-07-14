# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from unittest import mock

from sources.chrome_cookies import BrowserCookie
from sources import pixiv_browser_session
from sources.pixiv_browser_session import (
    PixivBrowserSession,
    PixivBrowserSessionError,
)


class PixivBrowserSessionTests(unittest.TestCase):
    def test_default_profile_is_fixed_and_separate_from_x(self):
        with mock.patch.dict(os.environ, {
                "LOCALAPPDATA": "C:/Users/Test/AppData/Local"}):
            session = PixivBrowserSession()
        normalized = session.profile_dir.replace("\\", "/")
        self.assertTrue(normalized.endswith(
            "DanbooruGrabber/PixivBrowserProfile"))
        self.assertNotIn("XBrowserProfile", normalized)
        self.assertTrue(session.state_path.endswith("PixivBrowserSession.json"))

    @mock.patch.object(pixiv_browser_session, "_wait_for_endpoint",
                       return_value="ws://127.0.0.1:9223/devtools/browser/pixiv-id")
    @mock.patch.object(pixiv_browser_session, "_launch_browser")
    @mock.patch.object(pixiv_browser_session, "_reserve_local_port", return_value=9223)
    @mock.patch.object(pixiv_browser_session, "_find_browser_executable",
                       return_value="C:/Chrome/chrome.exe")
    def test_open_login_uses_visible_dedicated_profile(
            self, _find, _port, launch, _wait):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        launch.return_value = mock.Mock(pid=432)
        with mock.patch.object(session, "_connection", return_value=None), \
             mock.patch.object(session, "_remove_state"), \
             mock.patch.object(session, "_write_state") as write_state:
            status = session.open_login()
        launch.assert_called_once_with(
            "C:/Chrome/chrome.exe", session.profile_dir, 9223,
            "https://accounts.pixiv.net/login", headless=False)
        self.assertTrue(status["running"])
        self.assertEqual(write_state.call_args.args[0]["mode"], "visible")

    def test_read_cookies_auto_starts_same_profile_headless(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        connection = {
            "websocket_url": "ws://127.0.0.1:9223/devtools/browser/pixiv-id",
            "mode": "headless",
        }
        raw = [{
            "name": "PHPSESSID", "value": "secret-session",
            "domain": ".pixiv.net",
        }]
        with mock.patch.object(
                session, "_connection", side_effect=[None, connection, connection]), \
             mock.patch.object(session, "launch") as launch, \
             mock.patch.object(session, "_shutdown_connection") as shutdown, \
             mock.patch.object(
                 pixiv_browser_session, "_read_all_cookies", return_value=raw):
            cookies = session.read_cookies()
        launch.assert_called_once_with(
            "https://accounts.pixiv.net/login", headless=True)
        self.assertEqual([cookie.name for cookie in cookies], ["PHPSESSID"])
        self.assertNotIn("secret-session", repr(cookies[0]))
        shutdown.assert_called_once_with(connection)

    def test_check_login_closes_visible_browser_after_login_is_saved(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        visible = {"pid": 1, "port": 9223, "mode": "visible"}
        cookie = BrowserCookie("PHPSESSID", "secret-session", ".pixiv.net")
        with mock.patch.object(session, "_connection", return_value=visible), \
             mock.patch.object(
                 session, "_read_cookies_from_connection", return_value=[cookie]), \
             mock.patch.object(session, "_shutdown_connection") as shutdown:
            status = session.check_login()
        shutdown.assert_called_once_with(visible)
        self.assertTrue(status["logged_in"])
        self.assertFalse(status["running"])
        self.assertIn("按需启动", status["message"])
        self.assertNotIn("secret-session", repr(status))

    def test_check_login_temporary_probe_closes_when_cookie_missing(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        headless = {"pid": 2, "port": 9224, "mode": "headless"}
        with mock.patch.object(
                session, "_connection", side_effect=[None, headless]), \
             mock.patch.object(
                 session, "_read_cookies_from_connection", return_value=[]), \
             mock.patch.object(session, "launch") as launch, \
             mock.patch.object(session, "_shutdown_connection") as shutdown:
            status = session.check_login()
        launch.assert_called_once_with(
            "https://accounts.pixiv.net/login", headless=True)
        shutdown.assert_called_once_with(headless)
        self.assertFalse(status["logged_in"])
        self.assertFalse(status["running"])

    def test_close_then_read_reopens_same_persistent_profile_headless(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        profile_before = session.profile_dir
        connection = {
            "websocket_url": "ws://127.0.0.1:9223/devtools/browser/pixiv-id",
            "mode": "visible",
        }
        with mock.patch.object(
                session, "_connection",
                side_effect=[connection, None, connection, connection]), \
             mock.patch.object(pixiv_browser_session, "_request_browser_close"), \
             mock.patch.object(pixiv_browser_session, "_stop_owned_process"), \
             mock.patch.object(session, "_shutdown_connection") as shutdown, \
             mock.patch.object(session, "_remove_state"), \
             mock.patch.object(session, "launch") as launch, \
             mock.patch.object(pixiv_browser_session, "_read_all_cookies", return_value=[{
                 "name": "PHPSESSID", "value": "persisted-secret",
                 "domain": ".pixiv.net",
             }]):
            session.close()
            cookies = session.read_cookies()
        self.assertEqual(session.profile_dir, profile_before)
        launch.assert_called_once_with(
            "https://accounts.pixiv.net/login", headless=True)
        self.assertEqual(cookies[0].name, "PHPSESSID")
        self.assertEqual(shutdown.call_count, 2)

    def test_temporary_headless_is_closed_even_when_cookie_read_fails(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        connection = {
            "websocket_url": "ws://127.0.0.1:9223/devtools/browser/pixiv-id",
            "mode": "headless",
        }
        with mock.patch.object(
                session, "_connection", side_effect=[None, connection, connection]), \
             mock.patch.object(session, "launch"), \
             mock.patch.object(session, "_shutdown_connection") as shutdown, \
             mock.patch.object(
                 pixiv_browser_session, "_read_all_cookies",
                 side_effect=RuntimeError("protocol detail")):
            with self.assertRaises(PixivBrowserSessionError):
                session.read_cookies()
        shutdown.assert_called_once_with(connection)

    def test_state_records_mode_but_never_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            session = PixivBrowserSession(
                profile_dir=os.path.join(directory, "PixivBrowserProfile"))
            session._write_state({
                "pid": 1, "port": 9223, "browser_id": "pixiv-id",
                "mode": "headless",
            })
            with open(session.state_path, "r", encoding="utf-8") as handle:
                state_text = handle.read()
            state = json.loads(state_text)
        self.assertEqual(state["mode"], "headless")
        self.assertNotIn("PHPSESSID", state_text)
        self.assertNotIn("secret", state_text)

    @mock.patch.object(pixiv_browser_session.subprocess, "Popen")
    def test_launcher_distinguishes_visible_and_headless(self, popen):
        popen.return_value = mock.Mock()
        pixiv_browser_session._launch_browser(
            "C:/Chrome/chrome.exe", "C:/Managed/PixivBrowserProfile", 9223,
            "https://accounts.pixiv.net/login", headless=False)
        visible_args = popen.call_args.args[0]
        self.assertNotIn("--headless=new", visible_args)
        self.assertIn("--new-window", visible_args)
        pixiv_browser_session._launch_browser(
            "C:/Chrome/chrome.exe", "C:/Managed/PixivBrowserProfile", 9223,
            "https://www.pixiv.net/", headless=True)
        headless_args = popen.call_args.args[0]
        self.assertIn("--headless=new", headless_args)
        self.assertNotIn("--new-window", headless_args)

    def test_windows_tree_kill_is_only_applied_to_owned_process(self):
        process = mock.Mock(pid=432)
        with mock.patch.object(pixiv_browser_session.os, "name", "nt"), \
             mock.patch.object(pixiv_browser_session.subprocess, "run") as run:
            pixiv_browser_session._stop_owned_process_tree(process)
        args = run.call_args.args[0]
        self.assertEqual(args[:2], ["taskkill", "/PID"])
        self.assertIn("/T", args)
        self.assertIn("/F", args)

    def test_recovered_dedicated_session_uses_verified_pid_tree_fallback(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        connection = {
            "pid": 432, "port": 9223,
            "websocket_url": "ws://127.0.0.1:9223/devtools/browser/pixiv-id",
            "mode": "headless",
        }
        with mock.patch.object(pixiv_browser_session.os, "name", "nt"), \
             mock.patch.object(pixiv_browser_session, "_request_browser_close"), \
             mock.patch.object(
                 pixiv_browser_session, "_wait_until_endpoint_closed",
                 side_effect=[False, True]), \
             mock.patch.object(
                 pixiv_browser_session, "_stop_process_tree_pid") as stop_tree, \
             mock.patch.object(session, "_remove_state") as remove_state:
            session._shutdown_connection(connection)
        stop_tree.assert_called_once_with(432)
        remove_state.assert_called_once()

    def test_cookie_file_is_securely_removed(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        cookie = BrowserCookie(
            "PHPSESSID", "secret-session", ".pixiv.net",
            secure=True, http_only=True)
        with mock.patch.object(session, "read_cookies", return_value=[cookie]):
            with session.cookie_file() as path:
                self.assertTrue(os.path.isfile(path))
            self.assertFalse(os.path.exists(path))

    def test_non_pixiv_login_url_is_rejected(self):
        session = PixivBrowserSession(profile_dir="C:/Managed/PixivBrowserProfile")
        with self.assertRaises(PixivBrowserSessionError) as raised:
            session.launch("https://example.com/")
        self.assertEqual(raised.exception.code, "invalid_url")


if __name__ == "__main__":
    unittest.main()
