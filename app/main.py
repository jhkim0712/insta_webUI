"""FastAPI app: Web UI, REST endpoints, media serving and RSS feeds."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, db, scheduler
from . import instaloader_service as svc
from .config import (
    DOWNLOADS_ROOT,
    HASHTAG_RE,
    PROFILE_RE,
    PUBLIC_BASE_URL,
    ensure_dirs,
    feed_targets,
    find_feed,
    load_settings,
    new_feed,
    resolve_download_dir,
    save_settings,
    session_file,
)
from .rss_generator import build_feed, media_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    db.init_db()
    scheduler.start(load_settings()["schedule"])
    yield
    scheduler.shutdown()


app = FastAPI(title="Instaloader Web UI", version=__version__, lifespan=lifespan)
ensure_dirs()
app.mount("/media", StaticFiles(directory=str(DOWNLOADS_ROOT)), name="media")


def base_url(request: Request) -> str:
    return PUBLIC_BASE_URL or str(request.base_url).rstrip("/")


def redirect(path: str, msg: str = "", level: str = "success") -> RedirectResponse:
    if msg:
        path += ("&" if "?" in path else "?") + urlencode({"msg": msg, "level": level})
    return RedirectResponse(path, status_code=303)


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.update(
        request=request,
        msg=request.query_params.get("msg", ""),
        level=request.query_params.get("level", "success"),
        base=base_url(request),
    )
    return templates.TemplateResponse(request, name, ctx)


def _parse_list(text: str, pattern, kind: str) -> list[str]:
    items: list[str] = []
    for raw in text.replace(",", "\n").splitlines():
        v = raw.strip().lstrip("@#")
        if not v:
            continue
        if not pattern.match(v):
            raise ValueError(f"잘못된 {kind}: {v}")
        if v.lower() not in (i.lower() for i in items):
            items.append(v)
    return items


# ------------------------------------------------------------------ pages --

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    settings = load_settings()
    b = base_url(request)
    feeds = [{"label": "전체", "url": f"{b}/rss", "enabled": True}]
    feeds += [{"label": f["name"], "url": f"{b}/rss/feed/{f['id']}", "enabled": f.get("enabled", True)}
              for f in settings["feeds"]]
    return render(
        request, "index.html",
        settings=settings,
        feeds=feeds,
        runs=db.recent_runs(10),
        counts=db.target_counts(),
        total=db.count_posts(),
        next_run=scheduler.next_run_time(),
        has_session=svc.has_session(settings.get("login_username", "")),
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings = load_settings()
    return render(
        request, "settings.html",
        settings=settings,
        downloads_root=str(DOWNLOADS_ROOT),
        has_session=svc.has_session(settings.get("login_username", "")),
        pending_2fa=request.query_params.get("twofa", ""),
    )


@app.post("/settings")
def save_settings_form(
    download_pictures: bool = Form(False),
    download_videos: bool = Form(False),
    download_video_thumbnails: bool = Form(False),
    download_comments: bool = Form(False),
    save_metadata: bool = Form(False),
    fast_update: bool = Form(False),
    max_posts_per_target: int = Form(20),
    schedule_mode: str = Form("disabled"),
    interval_minutes: int = Form(60),
    cron: str = Form("0 0 * * *"),
    download_subdir: str = Form(""),
    rss_title: str = Form("Instagram Feed"),
    rss_items_limit: int = Form(50),
):
    settings = load_settings()
    try:
        resolve_download_dir(download_subdir)
        if schedule_mode not in ("disabled", "interval", "cron"):
            raise ValueError("알 수 없는 스케줄 모드")
        schedule = {"mode": schedule_mode, "interval_minutes": max(1, interval_minutes), "cron": cron.strip()}
        scheduler.build_trigger(schedule)  # validates the cron expression
    except ValueError as e:
        return redirect("/settings", str(e), "danger")

    settings["options"] = {
        "download_pictures": download_pictures,
        "download_videos": download_videos,
        "download_video_thumbnails": download_video_thumbnails,
        "download_comments": download_comments,
        "save_metadata": save_metadata,
        "fast_update": fast_update,
        "max_posts_per_target": max(0, max_posts_per_target),
    }
    settings["schedule"] = schedule
    settings["download_subdir"] = download_subdir.strip().strip("/\\")
    settings["rss"] = {"title": rss_title.strip() or "Instagram Feed",
                       "items_limit": min(max(1, rss_items_limit), 500)}
    save_settings(settings)
    scheduler.apply_schedule(schedule)
    return redirect("/settings", "설정을 저장했습니다.")


@app.get("/posts", response_class=HTMLResponse)
def posts_page(request: Request, target: str = "", page: int = 1):
    page = max(1, page)
    per_page = 24
    settings = load_settings()
    targets, rss_url = None, "/rss"
    if target.startswith("feed:"):
        feed = find_feed(settings, target[5:])
        targets = feed_targets(feed) if feed else []
        rss_url = f"/rss/feed/{quote(target[5:])}"
    elif ":" in target:
        ttype, tname = target.split(":", 1)
        targets = [(ttype, tname)]
        rss_url = f"/rss/{quote(ttype)}/{quote(tname)}"
    posts = db.list_posts(targets, limit=per_page + 1, offset=(page - 1) * per_page)
    return render(
        request, "posts.html",
        posts=posts[:per_page],
        has_next=len(posts) > per_page,
        page=page,
        target=target,
        rss_url=rss_url,
        feeds=settings["feeds"],
        counts=db.target_counts(),
    )


# ------------------------------------------------------------------ feeds --

@app.get("/feeds", response_class=HTMLResponse)
def feeds_page(request: Request):
    settings = load_settings()
    counts = {(c["target_type"], c["target_name"].lower()): c["n"] for c in db.target_counts()}
    feeds = [{**f, "posts": sum(counts.get((t, n.lower()), 0) for t, n in feed_targets(f))}
             for f in settings["feeds"]]
    return render(request, "feeds.html", feeds=feeds)


@app.get("/feeds/new", response_class=HTMLResponse)
def feed_new_page(request: Request):
    return render(request, "feed_edit.html", feed=None)


@app.get("/feeds/{feed_id}", response_class=HTMLResponse)
def feed_edit_page(request: Request, feed_id: str):
    feed = find_feed(load_settings(), feed_id)
    if not feed:
        raise HTTPException(404)
    return render(request, "feed_edit.html", feed=feed)


def _feed_from_form(name: str, profiles: str, hashtags: str) -> tuple[str, list[str], list[str]]:
    name = name.strip()
    if not name:
        raise ValueError("피드 이름을 입력하세요.")
    p = _parse_list(profiles, PROFILE_RE, "계정명")
    h = _parse_list(hashtags, HASHTAG_RE, "해시태그")
    if not p and not h:
        raise ValueError("계정 또는 해시태그를 하나 이상 등록하세요.")
    return name, p, h


@app.post("/feeds")
def feed_create(name: str = Form(""), profiles: str = Form(""), hashtags: str = Form(""),
                enabled: bool = Form(False)):
    settings = load_settings()
    try:
        name, p, h = _feed_from_form(name, profiles, hashtags)
    except ValueError as e:
        return redirect("/feeds/new", str(e), "danger")
    settings["feeds"].append(new_feed(name, p, h, enabled))
    save_settings(settings)
    return redirect("/feeds", f"피드 '{name}'을(를) 만들었습니다.")


@app.post("/feeds/{feed_id}")
def feed_update(feed_id: str, name: str = Form(""), profiles: str = Form(""), hashtags: str = Form(""),
                enabled: bool = Form(False)):
    settings = load_settings()
    feed = find_feed(settings, feed_id)
    if not feed:
        raise HTTPException(404)
    try:
        name, p, h = _feed_from_form(name, profiles, hashtags)
    except ValueError as e:
        return redirect(f"/feeds/{feed_id}", str(e), "danger")
    feed.update(name=name, profiles=p, hashtags=h, enabled=enabled)
    save_settings(settings)
    return redirect("/feeds", f"피드 '{name}'을(를) 저장했습니다.")


@app.post("/feeds/{feed_id}/delete")
def feed_delete(feed_id: str):
    settings = load_settings()
    feed = find_feed(settings, feed_id)
    if not feed:
        raise HTTPException(404)
    settings["feeds"].remove(feed)
    save_settings(settings)
    return redirect("/feeds", f"피드 '{feed['name']}'을(를) 삭제했습니다. 수집된 게시물과 파일은 유지됩니다.")


@app.post("/feeds/{feed_id}/run")
def feed_run(feed_id: str):
    feed = find_feed(load_settings(), feed_id)
    if not feed:
        raise HTTPException(404)
    if svc.start_crawl_async("manual", feed_id):
        return redirect("/", f"피드 '{feed['name']}' 크롤링을 시작했습니다.")
    return redirect("/feeds", "이미 크롤링이 실행 중입니다.", "warning")


# ------------------------------------------------------------ crawl ctl ---

@app.post("/run")
def run_now():
    if svc.start_crawl_async("manual"):
        return redirect("/", "크롤링을 시작했습니다.")
    return redirect("/", "이미 크롤링이 실행 중입니다.", "warning")


@app.post("/stop")
def stop_crawl():
    if svc.state.running:
        svc.state.stop_requested = True
        return redirect("/", "중지를 요청했습니다. 현재 게시물 처리 후 멈춥니다.", "warning")
    return redirect("/", "실행 중인 크롤링이 없습니다.", "warning")


@app.get("/api/status")
def api_status():
    nrt = scheduler.next_run_time()
    return JSONResponse({
        "running": svc.state.running,
        "current": svc.state.current,
        "next_run": nrt.isoformat() if nrt else None,
        "logs": list(svc.state.logs)[-100:],
        "total_posts": db.count_posts(),
    })


# ------------------------------------------------------------------ login --

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    username = username.strip().lstrip("@")
    if not PROFILE_RE.match(username):
        return redirect("/settings", "잘못된 사용자명", "danger")
    try:
        result = svc.login(username, password)
    except ValueError as e:
        return redirect("/settings", str(e), "danger")
    if result == "2fa":
        return redirect(f"/settings?twofa={quote(username)}", "2단계 인증 코드를 입력하세요.", "info")
    _set_login_user(username)
    return redirect("/settings", f"{username} 로그인 성공 - 세션을 저장했습니다.")


@app.post("/login/2fa")
def login_2fa(username: str = Form(...), code: str = Form(...)):
    try:
        svc.login_2fa(username, code)
    except ValueError as e:
        return redirect("/settings", str(e), "danger")
    _set_login_user(username)
    return redirect("/settings", f"{username} 로그인 성공 - 세션을 저장했습니다.")


@app.post("/session/upload")
async def upload_session(username: str = Form(...), file: UploadFile = File(...)):
    username = username.strip().lstrip("@")
    if not PROFILE_RE.match(username):
        return redirect("/settings", "잘못된 사용자명", "danger")
    data = await file.read()
    if not data or len(data) > 1_000_000:
        return redirect("/settings", "세션 파일이 비어있거나 너무 큽니다.", "danger")
    session_file(username).write_bytes(data)
    _set_login_user(username)
    return redirect("/settings", f"{username} 세션 파일을 등록했습니다.")


@app.post("/logout")
def logout():
    settings = load_settings()
    user = settings.get("login_username", "")
    if user:
        session_file(user).unlink(missing_ok=True)
    settings["login_username"] = ""
    save_settings(settings)
    return redirect("/settings", "세션을 삭제했습니다.")


def _set_login_user(username: str) -> None:
    settings = load_settings()
    settings["login_username"] = username
    save_settings(settings)


# -------------------------------------------------------------------- rss --

def _rss(request: Request, targets: list[tuple[str, str]] | None, title: str, desc: str) -> Response:
    settings = load_settings()
    b = base_url(request)
    posts = db.list_posts(targets, limit=settings["rss"]["items_limit"])
    xml = build_feed(posts, b, title, b + request.url.path, desc)
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


@app.get("/rss")
def rss_all(request: Request):
    return _rss(request, None, load_settings()["rss"]["title"], "Instaloader로 수집한 Instagram 게시물")


@app.get("/rss/feed/{feed_id}")
def rss_feed(request: Request, feed_id: str):
    feed = find_feed(load_settings(), feed_id)
    if not feed:
        raise HTTPException(404)
    labels = [f"@{p}" for p in feed["profiles"]] + [f"#{h}" for h in feed["hashtags"]]
    return _rss(request, feed_targets(feed), feed["name"], "Instagram " + " ".join(labels))


@app.get("/rss/{target_type}/{name}")
def rss_target(request: Request, target_type: str, name: str):
    if target_type not in ("profile", "hashtag"):
        raise HTTPException(404)
    label = f"@{name}" if target_type == "profile" else f"#{name}"
    title = load_settings()["rss"]["title"]
    return _rss(request, [(target_type, name)], f"{title} - {label}", f"Instagram {label} 게시물")


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": __version__}


def _localtime(value) -> str:
    if not value:
        return "-"
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(scheduler.local_tz()).strftime("%Y-%m-%d %H:%M")


templates.env.globals["media_url"] = media_url
templates.env.globals["app_version"] = __version__
templates.env.filters["localtime"] = _localtime
