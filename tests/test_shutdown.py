import json
import os
import threading
import unittest
import urllib.request
from unittest import mock

import app


class DummyTask:
    def __init__(self):
        self.status = "running"
        self.stop_flag = False
        self.logs = []

    def log(self, message):
        self.logs.append(message)


class ShutdownTests(unittest.TestCase):
    def test_managed_session_cleanup_is_best_effort(self):
        x_module = mock.Mock()
        x_module.close.side_effect = RuntimeError("secret-bearing failure")
        pixiv_module = mock.Mock()
        with mock.patch.object(app, "_x_browser_session_module", return_value=x_module), \
                mock.patch.object(app, "_pixiv_browser_session_module", return_value=pixiv_module):
            app.close_managed_browser_sessions()
        x_module.close.assert_called_once_with()
        pixiv_module.close.assert_called_once_with()

    def test_shutdown_endpoint_stops_task_and_server_after_response(self):
        old_task = app.CURRENT_TASK
        task = DummyTask()
        app.CURRENT_TASK = task
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:%d/api/shutdown" % server.server_port,
                data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            with mock.patch.object(app, "close_managed_browser_sessions") as close_sessions:
                with urllib.request.urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            thread.join(3)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["message"], "后台已关闭，可关闭页面")
            self.assertTrue(task.stop_flag)
            self.assertFalse(thread.is_alive())
            close_sessions.assert_called_once_with()
        finally:
            server.server_close()
            app.CURRENT_TASK = old_task

    def test_frontend_has_confirmed_shutdown_and_disables_controls(self):
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "static", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        with open(os.path.join(root, "static", "app.js"), encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn('id="shutdownBtn"', html)
        self.assertIn('id="shutdownResult"', html)
        self.assertIn('window.confirm(', script)
        self.assertIn('/api/shutdown', script)
        self.assertIn('document.querySelectorAll("button,input,select,textarea")', script)


if __name__ == "__main__":
    unittest.main()
