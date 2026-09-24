# Project Overview: Instaloader Web UI & RSS Service (Dockerized)

**Instaloader**로 인스타그램 게시물을 수집하는 컨테이너(Docker) 애플리케이션입니다. 수집 대상과 주기는 Web UI에서 관리하고, 수집한 콘텐츠는 **피드(Feed)** 단위의 RSS로 제공합니다.

- 저장소: https://github.com/jhkim0712/insta_webUI
- 이미지: `ghcr.io/jhkim0712/insta_webui`
- 현재 버전: `app/__init__.py`의 `__version__` (변경 내역은 `CHANGELOG.md`)

---

## 1. Core Requirements (핵심 요구사항)

1. **Docker 기반 실행 환경**
   - `docker compose up -d` 한 번으로 전체 서비스가 떠야 합니다.
   - 설정(`/config`), DB(`/data`), 미디어(`/downloads`)는 볼륨으로 보존합니다.

2. **피드(Feed) 관리**
   - 피드는 **이름 + 계정 목록 + 해시태그 목록 + 활성 여부**로 이루어지며, 여러 개를 만들 수 있습니다.
     - 예: A 피드 = `#travel`, `#서울` / B 피드 = `@nasa`, `@spacex`
   - 피드마다 고유한 RSS 주소 `/rss/feed/<id>`가 있습니다. **이름이나 대상을 바꿔도 id(=RSS 주소)는 바뀌지 않아야 합니다.**
   - 같은 대상이 여러 피드에 있어도 **한 번만 수집**하고, 해당 피드 모두에 나타납니다.
   - 비활성 피드는 스케줄 수집에서 빠지지만 RSS는 계속 제공합니다.
   - 피드만 따로 즉시 수집할 수 있어야 합니다 (**이 피드만 실행**).

3. **Web UI**
   - 다운로드 옵션(사진, 동영상, 썸네일, 댓글, 메타데이터, 빠른 업데이트, 대상별 최대 게시물 수)
   - 스케줄: 비활성 / 주기(분) / Cron 표현식, **지금 실행**, 중지
   - 다운로드 경로: `/downloads` 아래 하위 경로만 허용 (RSS가 `/media`로 제공하기 때문)
   - Instagram 로그인 (2단계 인증 포함) 또는 세션 파일 업로드. 비밀번호는 저장하지 않습니다.
   - 옵션, 스케줄, 경로는 **모든 피드에 공통**입니다.

4. **RSS 서비스**
   - RSS 2.0. 게시물의 **이미지·동영상과 캡션**을 `content:encoded`/`description`에 인라인 HTML로 넣어, RSS 리더에서 이미지가 바로 보여야 합니다.
   - `enclosure`, `media:content`, `media:thumbnail`(Media RSS)도 함께 제공합니다.
   - 주소: `/rss/feed/<id>`(피드), `/rss`(전체), `/rss/profile/<name>`, `/rss/hashtag/<tag>`(대상별)

---

## 2. Technical Stack (사용 중인 기술)

- **Python 3.12** (이미지 기준, 3.10 이상에서 동작), `instaloader`
- **FastAPI + Uvicorn**: Web UI, REST, RSS, 정적 미디어(`/media`)
- **APScheduler 3.x** (`BackgroundScheduler`): 단일 크롤링 잡 (`coalesce`, `max_instances=1`)
- **Jinja2 + Bootstrap 5** (CDN), 약간의 vanilla JS (상태 폴링, 복사 버튼)
- **SQLite** (표준 라이브러리 `sqlite3`), **JSON** 설정 파일
- **Docker / Docker Compose**, **GitHub Actions → GHCR** (amd64·arm64)

---

## 3. Architecture & Directory Structure

```text
.
├── Dockerfile
├── docker-compose.yml          # image: ghcr.io/...:latest + build: .
├── requirements.txt
├── CHANGELOG.md
├── .github/workflows/docker.yml
├── config/                     # settings.json, session-<user> (git 제외)
├── data/                       # insta.db (git 제외)
├── downloads/                  # 미디어 (git 제외)
└── app/
    ├── __init__.py             # __version__
    ├── main.py                 # 라우트: 대시보드 / 피드 / 설정 / 게시물 / 로그인 / RSS / healthz
    ├── config.py               # 경로·환경변수, settings.json 로드·저장·마이그레이션, 피드 도우미 함수
    ├── db.py                   # posts, runs 테이블
    ├── instaloader_service.py  # 로그인·세션, 크롤링 (CrawlState: 실행 상태·로그 링버퍼)
    ├── scheduler.py            # APScheduler 트리거 구성, 시간대(TZ)
    ├── rss_generator.py        # RSS XML 생성
    └── templates/              # base, index, feeds, feed_edit, settings, posts
```

### 데이터 모델

**`/config/settings.json`**
```json
{
  "feeds": [{"id": "a1b2c3d4", "name": "여행", "profiles": [], "hashtags": ["travel"], "enabled": true}],
  "options": {"download_pictures": true, "download_videos": true, "download_video_thumbnails": true,
              "download_comments": false, "save_metadata": true, "fast_update": true, "max_posts_per_target": 20},
  "schedule": {"mode": "disabled|interval|cron", "interval_minutes": 60, "cron": "0 0 * * *"},
  "download_subdir": "",
  "login_username": "",
  "rss": {"title": "Instagram Feed", "items_limit": 50}
}
```

**SQLite `/data/insta.db`**
- `posts`: `shortcode`(PK), `target_type`(`profile`|`hashtag`), `target_name`, `owner`, `caption`, `date_utc`, `is_video`, `media`(JSON: `[{type, path, poster?}]`, 경로는 `DOWNLOADS_ROOT` 기준 상대 경로), `likes`, `created_at`
- `runs`: 실행 이력 (`trigger`, `status`: running/success/error/stopped/aborted, `new_posts`, `message`)

게시물은 **대상(target)** 에 속하고, 피드와는 직접 연결되지 않습니다. 피드 RSS는 "그 피드에 들어 있는 대상들의 게시물"을 조회해서 만듭니다 (`db.list_posts(targets)`). 그래서 피드를 삭제하거나 수정해도 게시물은 남습니다.

### 크롤링 흐름
1. `crawl_targets(settings, feed_id=None)`: 활성 피드(또는 지정한 피드 하나)의 대상을 모으고, 대소문자 구분 없이 중복을 없앱니다.
2. 대상마다 Instaloader로 게시물을 순회합니다. 저장 위치는 `<download_dir>/<계정>` 또는 `<download_dir>/hashtag_<태그>`, 파일 이름은 `{shortcode}`(`_N`) 형식입니다.
3. 다운로드한 파일을 모아 미디어 목록을 만들고 `posts`에 upsert합니다.
4. 계정 대상에서 `fast_update`가 켜져 있으면, 이미 있는 게시물(고정 게시물 제외)을 만나는 즉시 멈춥니다.

---

## 4. 규칙 (Conventions)

- **경로 안전성**: 사용자가 입력한 경로는 `resolve_download_dir()`로 `DOWNLOADS_ROOT` 밖을 거부합니다. 계정명과 태그는 `PROFILE_RE`/`HASHTAG_RE`로 검증합니다.
- **설정 스키마 변경**: `DEFAULT_SETTINGS`에 기본값을 추가하고(`_merge`가 채움), 구조가 바뀌면 `config._migrate()`에 변환 로직을 넣습니다. 마이그레이션한 결과는 즉시 저장해서 생성된 id가 바뀌지 않게 합니다.
- **민감 정보**: `config/`(세션 파일)는 절대 커밋하지 않습니다 (`.gitignore`).
- **UI 문구**는 한국어입니다. 폼 처리는 POST 후 303 리다이렉트이고, 메시지는 `?msg=&level=` 쿼리로 전달합니다.
- **시간**: DB에는 UTC ISO 문자열로 저장하고, 화면에서는 `localtime` 필터로 `TZ` 시간대로 바꿔 보여 줍니다.

## 5. 개발·테스트

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload       # config/ data/ downloads/ 는 현재 디렉터리에 생성
```

- 테스트는 `fastapi.testclient.TestClient`(httpx 필요)와 임시 `CONFIG_DIR`/`DATA_DIR`/`DOWNLOADS_ROOT`로 합니다. 실제 인스타그램에 요청하면 요청 제한(429)에 걸려 오래 대기할 수 있으므로, `db.upsert_post()`로 가짜 게시물을 넣어 RSS와 화면을 검증합니다.
- CI(`check` 잡)는 `compileall`과 `import app.main`으로 스모크 테스트를 합니다.

## 6. 버전 · 릴리스

- SemVer를 따르고, 기준은 `app/__init__.py`의 `__version__`입니다. 새 기능은 minor, 버그 수정은 patch를 올립니다.
- 릴리스 순서: `__version__` 올리기 → `CHANGELOG.md` 작성 → 커밋 → `vX.Y.Z` 태그 push
- CI 동작: PR은 빌드만 하고, `main` push는 `latest`와 `sha-*` 이미지를 올리며, `v*` 태그는 `X.Y.Z`와 `X.Y` 이미지를 올리고 GitHub Release를 만듭니다. 태그와 `__version__`이 다르면 CI가 실패합니다.
