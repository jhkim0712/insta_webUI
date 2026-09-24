"""Instaloader integration: login/session handling and the crawl job itself."""
import collections
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import instaloader
from instaloader.exceptions import (
    BadCredentialsException,
    InstaloaderException,
    TwoFactorAuthRequiredException,
)

from . import db
from .config import DOWNLOADS_ROOT, load_settings, resolve_download_dir, session_file

log = logging.getLogger("crawler")

MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}
_INDEX_RE = re.compile(r"_(\d+)$")


class CrawlState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.stop_requested = False
        self.current = ""
        self.logs: collections.deque[str] = collections.deque(maxlen=300)

    def add_log(self, msg: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{stamp}] {msg}")
        log.info(msg)


state = CrawlState()

# Instaloader instance waiting for a 2FA code between two HTTP requests.
_pending_2fa: dict[str, instaloader.Instaloader] = {}


def _new_loader(options: dict | None = None, dirname_pattern: str = "{target}") -> instaloader.Instaloader:
    o = options or {}
    return instaloader.Instaloader(
        download_pictures=o.get("download_pictures", True),
        download_videos=o.get("download_videos", True),
        download_video_thumbnails=o.get("download_video_thumbnails", True),
        download_geotags=False,
        download_comments=o.get("download_comments", False),
        save_metadata=o.get("save_metadata", True),
        compress_json=True,
        post_metadata_txt_pattern="{caption}",
        dirname_pattern=dirname_pattern,
        filename_pattern="{shortcode}",
        quiet=True,
        max_connection_attempts=3,
    )


# ---------------------------------------------------------------- login ----

def login(username: str, password: str) -> str:
    """Returns 'ok' or '2fa'. Raises ValueError with a user-facing message."""
    L = _new_loader()
    try:
        L.login(username, password)
    except TwoFactorAuthRequiredException:
        _pending_2fa[username] = L
        return "2fa"
    except BadCredentialsException:
        raise ValueError("아이디 또는 비밀번호가 올바르지 않습니다.")
    except InstaloaderException as e:
        raise ValueError(f"로그인 실패: {e}")
    L.save_session_to_file(str(session_file(username)))
    return "ok"


def login_2fa(username: str, code: str) -> None:
    L = _pending_2fa.get(username)
    if L is None:
        raise ValueError("진행 중인 2단계 인증이 없습니다. 다시 로그인하세요.")
    try:
        L.two_factor_login(code.strip())
    except InstaloaderException as e:
        raise ValueError(f"2단계 인증 실패: {e}")
    _pending_2fa.pop(username, None)
    L.save_session_to_file(str(session_file(username)))


def has_session(username: str) -> bool:
    return bool(username) and session_file(username).exists()


# ---------------------------------------------------------------- crawl ----

def _collect_media(target_dir: Path, shortcode: str) -> list[dict]:
    """Group downloaded files ({sc}.ext / {sc}_N.ext) into ordered media items."""
    stems: dict[str, dict[str, Path]] = {}
    for f in target_dir.glob(f"{shortcode}*"):
        if f.suffix.lower() not in MEDIA_EXTS:
            continue
        if f.stem != shortcode and not f.stem.startswith(shortcode + "_"):
            continue
        stems.setdefault(f.stem, {})[f.suffix.lower()] = f

    def order(stem: str) -> int:
        m = _INDEX_RE.search(stem[len(shortcode):])
        return int(m.group(1)) if m else 0

    items = []
    for stem in sorted(stems, key=order):
        files = stems[stem]
        rel = lambda p: p.relative_to(DOWNLOADS_ROOT).as_posix()  # noqa: E731
        image = next((files[e] for e in (".jpg", ".jpeg", ".png", ".webp") if e in files), None)
        if ".mp4" in files:
            items.append({"type": "video", "path": rel(files[".mp4"]),
                          "poster": rel(image) if image else None})
        elif image:
            items.append({"type": "image", "path": rel(image)})
    return items


def _iter_posts(L: instaloader.Instaloader, target_type: str, name: str):
    if target_type == "profile":
        return instaloader.Profile.from_username(L.context, name).get_posts()
    tag = instaloader.Hashtag.from_name(L.context, name)
    if hasattr(tag, "get_posts_resumable"):
        return tag.get_posts_resumable()
    return tag.get_posts()


def _crawl_target(L, base_dir: Path, target_type: str, name: str, options: dict) -> int:
    folder = name if target_type == "profile" else f"hashtag_{name}"
    target_dir = base_dir / folder
    L.dirname_pattern = str(base_dir / "{target}")
    max_posts = int(options.get("max_posts_per_target") or 0)
    fast_update = options.get("fast_update", True)

    new = 0
    seen = 0
    for post in _iter_posts(L, target_type, name):
        if state.stop_requested:
            break
        if max_posts and seen >= max_posts:
            break
        seen += 1
        if db.post_exists(post.shortcode):
            # Profile feeds are chronological (pinned posts aside), so an
            # already-known post means everything after it is known too.
            if fast_update and target_type == "profile" and not getattr(post, "is_pinned", False):
                break
            continue

        state.current = f"{target_type}:{name} / {post.shortcode}"
        L.download_post(post, target=folder)
        media = _collect_media(target_dir, post.shortcode)
        db.upsert_post({
            "shortcode": post.shortcode,
            "target_type": target_type,
            "target_name": name,
            "owner": post.owner_username,
            "caption": post.caption or "",
            "date_utc": post.date_utc.replace(tzinfo=timezone.utc).isoformat(),
            "is_video": int(bool(post.is_video)),
            "media": media,
            "likes": post.likes,
        })
        new += 1
    return new


def run_crawl(trigger: str = "schedule") -> None:
    with state.lock:
        if state.running:
            state.add_log(f"이미 실행 중이므로 건너뜀 (trigger={trigger})")
            return
        state.running = True
        state.stop_requested = False

    run_id = db.start_run(trigger)
    total_new = 0
    errors: list[str] = []
    try:
        settings = load_settings()
        options = settings["options"]
        base_dir = resolve_download_dir(settings.get("download_subdir", ""))
        base_dir.mkdir(parents=True, exist_ok=True)

        L = _new_loader(options)
        user = settings.get("login_username", "")
        if has_session(user):
            L.load_session_from_file(user, str(session_file(user)))
            state.add_log(f"세션 로드: {user}")
        else:
            state.add_log("로그인 세션 없음 - 비로그인 상태로 수집 (제한될 수 있음)")

        targets = [("profile", p) for p in settings["profiles"]] + \
                  [("hashtag", h) for h in settings["hashtags"]]
        if not targets:
            state.add_log("수집 대상이 없습니다.")
        state.add_log(f"크롤링 시작 (trigger={trigger}, 대상 {len(targets)}개)")

        for target_type, name in targets:
            if state.stop_requested:
                state.add_log("사용자 요청으로 중지")
                break
            state.current = f"{target_type}:{name}"
            try:
                n = _crawl_target(L, base_dir, target_type, name, options)
                total_new += n
                state.add_log(f"{target_type}:{name} 완료 - 신규 {n}개")
            except Exception as e:  # keep going with the next target
                errors.append(f"{target_type}:{name}: {e}")
                state.add_log(f"{target_type}:{name} 실패 - {e}")

        status = "stopped" if state.stop_requested else ("error" if errors else "success")
        db.finish_run(run_id, status, total_new, "; ".join(errors)[:2000])
        state.add_log(f"크롤링 종료 - 상태 {status}, 신규 {total_new}개")
    except Exception as e:
        db.finish_run(run_id, "error", total_new, str(e)[:2000])
        state.add_log(f"크롤링 오류: {e}")
    finally:
        state.running = False
        state.stop_requested = False
        state.current = ""


def start_crawl_async(trigger: str = "manual") -> bool:
    if state.running:
        return False
    threading.Thread(target=run_crawl, args=(trigger,), daemon=True, name="crawl").start()
    return True
