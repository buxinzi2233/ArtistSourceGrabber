"""Enabled source registry.

Only explicitly reviewed sources are exposed here.  The repository also contains
adapters for disabled/controversial sites; importing this registry must never
enable them by accident.
"""

from .danbooru import DanbooruSource
from .gelbooru import GelbooruSource, SafebooruSource
from .moebooru import KonachanSource, YandereSource
from .openverse import OpenverseSource
from .pixiv import PixivSource
from .twitter import TwitterXSource


_SOURCE_LIST = [
    DanbooruSource(),
    TwitterXSource(),
    OpenverseSource(),
    PixivSource(),
    GelbooruSource(),
    SafebooruSource(),
    KonachanSource(),
    YandereSource(),
]

SOURCES = {source.id: source for source in _SOURCE_LIST}


SOURCE_METADATA = {
    "danbooru": {
        "description": "官方公开 API；支持画师 ID、tag 与模糊候选搜索。",
        "auth_fields": [
            {"id": "login", "label": "用户名", "secret": False, "required": False},
            {"id": "api_key", "label": "API Key", "secret": True, "required": False},
        ],
        "ratings": [["", "全部"], ["g", "General"], ["s", "Sensitive"],
                    ["q", "Questionable"], ["e", "Explicit"]],
    },
    "twitter": {
        "description": "使用 gallery-dl 抓取目标画师媒体；推荐在应用专用 X 窗口登录一次，目标账号与登录账号彼此独立。",
        "auth_fields": [
            {"id": "auth_token", "label": "X auth_token Cookie", "secret": True, "required": False},
            {"id": "ct0", "label": "X ct0 Cookie", "secret": True, "required": False},
            {"id": "x_cookies_file", "label": "完整 cookies.txt 路径（推荐）", "secret": False, "required": False},
        ],
        "ratings": [["", "不筛选"]],
        "warning": "Chrome v20 Cookie 无法可靠从日常 Profile 复制解密；请优先使用专用 X 登录窗口。兼容模式仍保留手输 Cookie、cookies.txt 与浏览器读取。",
        "extra_fields": [
            {"id": "x_mode", "label": "抓取范围", "type": "select",
             "options": [["media_user", "目标账号媒体"], ["tweets_user", "目标账号推文"],
                         ["likes", "登录账号自己的 Likes"]]},
            {"id": "x_cookies_from_browser", "label": "直接读取浏览器 Cookie", "type": "select",
             "options": [["", "不使用"], ["auto", "自动检测（推荐）"],
                         ["chrome", "Chrome"], ["edge", "Edge"],
                         ["firefox", "Firefox"], ["brave", "Brave"], ["chromium", "Chromium"]]},
            {"id": "x_browser_profile", "label": "浏览器 Profile（可选）", "type": "text",
             "placeholder": "如 Profile 1；留空时自动尝试"},
        ],
    },
    "pixiv": {
        "description": "支持专用 Pixiv 登录窗口、公开网页模式与 App API；优先使用 Danbooru 记录中的数字用户 ID。",
        "auth_fields": [
            {"id": "access_token", "label": "Pixiv access_token", "secret": True, "required": False},
            {"id": "phpsessid", "label": "Pixiv PHPSESSID", "secret": True, "required": False},
        ],
        "ratings": [["", "全部"], ["safe", "Safe"], ["r18", "R18"]],
    },
    "openverse": {
        "description": "开放许可图片聚合 API；保留作者、原始作品页与许可证。",
        "auth_fields": [], "ratings": [["", "由许可筛选控制"]],
        "extra_fields": [
            {"id": "openverse_license", "label": "许可用途", "type": "select",
             "options": [["all", "全部开放许可"], ["commercial", "允许商业使用"],
                         ["modification", "允许修改"]]},
        ],
    },
    "gelbooru": {
        "description": "Gelbooru DAPI；当前公开接口要求 User ID 与 API Key。",
        "auth_fields": [
            {"id": "user_id", "label": "User ID", "secret": False, "required": True},
            {"id": "api_key", "label": "API Key", "secret": True, "required": True},
        ],
        "ratings": [["", "全部"], ["general", "General"], ["sensitive", "Sensitive"],
                    ["questionable", "Questionable"], ["explicit", "Explicit"]],
    },
    "safebooru": {
        "description": "Safebooru.org DAPI；全年龄向来源。",
        "auth_fields": [], "ratings": [["", "全部"]],
    },
    "konachan": {
        "description": "Konachan Moebooru API。",
        "auth_fields": [],
        "ratings": [["", "全部"], ["s", "Safe"], ["q", "Questionable"], ["e", "Explicit"]],
    },
    "yandere": {
        "description": "yande.re Moebooru API。",
        "auth_fields": [],
        "ratings": [["", "全部"], ["s", "Safe"], ["q", "Questionable"], ["e", "Explicit"]],
    },
}


def get_source(source_id):
    return SOURCES.get(str(source_id or "danbooru").strip().lower())


def list_sources():
    result = []
    for source in _SOURCE_LIST:
        meta = dict(SOURCE_METADATA.get(source.id, {}))
        meta.update({
            "id": source.id,
            "label": source.label,
            "needs_auth": bool(source.needs_auth),
            "supports_artist_search": bool(source.supports_artist_search),
            "can_count": bool(source.can_count),
        })
        result.append(meta)
    return result
