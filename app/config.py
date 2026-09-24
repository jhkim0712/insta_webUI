"""Paths and persistent user settings (stored as JSON in CONFIG_DIR)."""
import json
import os
import re
import threading
from copy import deepcopy
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "./config")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
DOWNLOADS_ROOT = Path(os.environ.get("DOWNLOADS_ROOT", "./downloads")).resolve()
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

SETTINGS_FILE = CONFIG_DIR / "settings.json"
DB_FILE = DATA_DIR / "insta.db"

PROFILE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
HASHTAG_RE = re.compile(r"^\w{1,100}$", re.UNICODE)

DEFAULT_SETTINGS = {
    "profiles": [],
    "hashtags": [],
    "options": {
        "download_pictures": True,
        "download_videos": True,
        "download_video_thumbnails": True,
        "download_comments": False,
        "save_metadata": True,
        "fast_update": True,
        "max_posts_per_target": 20,
    },
    "schedule": {
        "mode": "disabled",  # disabled | interval | cron
        "interval_minutes": 60,
        "cron": "0 0 * * *",
    },
    # Relative to DOWNLOADS_ROOT, so media stays servable for RSS.
    "download_subdir": "",
    "login_username": "",
    "rss": {
        "title": "Instagram Feed",
        "items_limit": 50,
    },
}

_lock = threading.Lock()


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, DOWNLOADS_ROOT):
        d.mkdir(parents=True, exist_ok=True)


def _merge(defaults: dict, loaded: dict) -> dict:
    out = deepcopy(defaults)
    for k, v in loaded.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> dict:
    with _lock:
        if not SETTINGS_FILE.exists():
            return deepcopy(DEFAULT_SETTINGS)
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deepcopy(DEFAULT_SETTINGS)
        return _merge(DEFAULT_SETTINGS, data)


def save_settings(settings: dict) -> None:
    with _lock:
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_FILE)


def resolve_download_dir(subdir: str) -> Path:
    """Resolve a user-supplied subdir, refusing anything outside DOWNLOADS_ROOT."""
    sub = (subdir or "").strip().strip("/\\")
    target = (DOWNLOADS_ROOT / sub).resolve()
    if target != DOWNLOADS_ROOT and DOWNLOADS_ROOT not in target.parents:
        raise ValueError(f"다운로드 경로는 {DOWNLOADS_ROOT} 내부여야 합니다.")
    return target


def session_file(username: str) -> Path:
    return CONFIG_DIR / f"session-{username}"
