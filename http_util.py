# -*- coding: utf-8 -*-
"""共享 HTTP / 错误处理工具,所有源的客户代码共享。"""
import json
import socket
import urllib.error
import urllib.request


UA = "MultiBooruGrabber/2.0 (personal archival tool; python-urllib)"


def build_opener(proxy=None):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def http_request(url, proxy=None, headers=None, timeout=30, method="GET",
                 body=None, raw=False):
    """发起一次 HTTP 请求,返回 bytes 或解析后的 JSON。

    body: bytes 或 None(POST/PUT)。raw: True 返回 (status, bytes),False 返回已解析 JSON。
    """
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method=method)
    if body is not None:
        req.data = body
        req_headers.setdefault("Content-Type", "application/json")
        req.add_header("Content-Type", req_headers["Content-Type"])
    opener = build_opener(proxy)
    try:
        resp = opener.open(req, timeout=timeout)
        data = resp.read()
        status = resp.getcode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            data = exc.read()
        except Exception:
            data = b""
        resp = type("R", (), {"getcode": lambda self: status, "read": lambda self: data})()
        # re-raise below if not consumed
        if raw:
            return status, data
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            raise exc
    if raw:
        return status, data
    ctype = (resp.headers.get("Content-Type") or "") if hasattr(resp, "headers") else ""
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return data.decode("utf-8", errors="replace")


def http_get_bytes(url, proxy=None, headers=None, timeout=180):
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    return build_opener(proxy).open(req, timeout=timeout).read()


def describe_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            raw = exc.read()
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                detail = data.get("message") or data.get("error") or ""
                if not detail:
                    detail = ";".join(
                        "%s:%s" % (k, v) for k, v in data.items() if k != "success"
                    )[:400]
        except Exception:
            pass
        hints = {
            401: "认证失败,请检查账号 / Key / Token",
            403: "无权限或被站点防护拦截",
            404: "资源不存在",
            410: "请求页数超出等级允许范围",
            422: "搜索条件超出等级限制",
            429: "被限流,请稍后重试",
        }
        parts = ["HTTP %d" % exc.code]
        if exc.code in hints:
            parts.append(hints[exc.code])
        if detail:
            parts.append(detail[:300])
        return ",".join(parts)
    if isinstance(exc, socket.timeout):
        return "连接超时(可能需要代理)"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", exc)
        return "网络错误:%s(可能需要代理)" % reason
    return str(exc)