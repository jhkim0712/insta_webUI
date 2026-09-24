# Insta WebUI

[![Build & Release](https://github.com/jhkim0712/insta_webUI/actions/workflows/docker.yml/badge.svg)](https://github.com/jhkim0712/insta_webUI/actions/workflows/docker.yml)
[![GHCR](https://img.shields.io/badge/ghcr.io-jhkim0712%2Finsta__webui-blue?logo=docker)](https://github.com/jhkim0712/insta_webUI/pkgs/container/insta_webui)

[Instaloader](https://instaloader.github.io/)로 인스타그램 게시물을 수집하는 Docker 앱입니다. 웹 화면에서 수집 대상과 주기를 관리하고, 수집한 게시물을 **이미지·동영상·캡션이 들어간 RSS 피드**로 제공합니다.

## 주요 기능

- **여러 피드 관리**: 피드마다 이름을 붙이고 계정·해시태그를 묶어서 등록합니다. 피드마다 RSS 주소가 따로 나옵니다. 예를 들어 "여행" 피드에는 `#travel`, `#서울`을, "우주" 피드에는 `@nasa`, `@spacex`를 넣을 수 있습니다.
- **Web UI**: 다운로드 옵션(사진, 동영상, 썸네일, 댓글, 메타데이터)과 스케줄을 설정합니다.
- **스케줄링**: 분 단위 주기나 Cron 표현식으로 자동 수집하고, **지금 실행** 버튼으로 바로 수집할 수도 있습니다.
- **다운로드 경로 지정**: `/downloads` 아래 원하는 폴더에 계정·해시태그별로 저장합니다.
- **RSS 2.0 피드**: 피드별, 전체, 계정별, 해시태그별 RSS를 제공합니다. 본문(`content:encoded`)에 이미지와 동영상을 넣고 `enclosure`와 Media RSS 태그도 붙여서 RSS 리더에 미디어가 바로 보입니다.
- **로그인 세션**: 웹에서 로그인(2단계 인증 지원)하거나 세션 파일을 업로드합니다. 비밀번호는 저장하지 않습니다.
- **대시보드**: 실시간 로그, 실행 이력, 대상별 수집 현황, 게시물 갤러리를 보여 줍니다.

## 빠른 시작

### 1) 배포된 이미지로 실행 (권장)

```bash
mkdir insta-webui && cd insta-webui
curl -O https://raw.githubusercontent.com/jhkim0712/insta_webUI/main/docker-compose.yml
docker compose pull
docker compose up -d
```

또는 `docker run`으로 실행할 수도 있습니다.

```bash
docker run -d --name insta-webui -p 8000:8000 \
  -e TZ=Asia/Seoul \
  -v "$PWD/config:/config" -v "$PWD/data:/data" -v "$PWD/downloads:/downloads" \
  ghcr.io/jhkim0712/insta_webui:latest
```

### 2) 소스에서 빌드

```bash
git clone https://github.com/jhkim0712/insta_webUI.git
cd insta_webUI
docker compose up -d --build
```

실행한 뒤 브라우저에서 `http://<호스트>:8000`에 접속합니다.

> 릴리스 페이지의 `insta-webui-vX.Y.Z.tar.gz`에는 버전이 고정된 `docker-compose.yml`이 들어 있습니다. 압축을 풀고 `docker compose up -d`만 실행하면 됩니다.

## 사용 방법

1. **설정 → Instagram 로그인**에서 로그인하거나 세션 파일을 업로드합니다.
   - 로그인하지 않으면 수집이 크게 제한됩니다. 해시태그와 댓글은 로그인해야만 받을 수 있습니다.
   - 로컬에서 `instaloader -l USERNAME`으로 만든 세션 파일(`~/.config/instaloader/session-USERNAME`)도 업로드할 수 있습니다.
2. **피드 → 새 피드**에서 피드 이름과 계정·해시태그를 등록합니다. 필요한 만큼 피드를 만들 수 있습니다.
   - 같은 계정이나 태그가 여러 피드에 들어 있어도 한 번만 수집하고, 각 피드에 모두 나타납니다.
   - **자동 수집 활성**을 끄면 스케줄 수집에서 빠집니다. 이미 수집한 게시물의 RSS는 계속 제공됩니다.
   - **이 피드만 실행**으로 해당 피드의 대상만 바로 수집할 수 있습니다.
3. **설정**에서 다운로드 옵션, 스케줄, 다운로드 경로를 입력하고 저장합니다. 이 설정은 모든 피드에 공통으로 적용됩니다.
   - 스케줄 모드: 비활성 / 주기(분) / Cron (`0 0 * * *`은 매일 자정)
   - 다운로드 경로는 `/downloads` 안쪽만 쓸 수 있습니다. RSS가 이 경로의 미디어를 제공하기 때문입니다.
4. **대시보드 → 지금 실행**을 누르면 활성 피드 전체를 바로 수집합니다.
5. 대시보드나 피드 화면에 나온 RSS 주소를 RSS 리더에 등록합니다.

## RSS 피드

| 피드 | 주소 |
|---|---|
| 피드별 | `/rss/feed/<feed-id>` (피드 화면에서 복사) |
| 전체 | `/rss` |
| 계정별 | `/rss/profile/<username>` |
| 해시태그별 | `/rss/hashtag/<tag>` |

피드 이름을 바꾸거나 대상을 수정해도 피드 id는 그대로여서 RSS 주소가 바뀌지 않습니다. 이전 버전에서 등록한 계정·해시태그는 처음 실행할 때 **기본 피드**로 자동으로 옮겨집니다.

RSS 리더가 이미지를 불러오려면 이 서버의 `/media/...` 주소에 접근할 수 있어야 합니다. 외부 도메인이나 리버스 프록시 뒤에서 운영한다면 `PUBLIC_BASE_URL`을 지정하세요.

## 설정

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `TZ` | `UTC` (compose에서는 `Asia/Seoul`) | 스케줄과 화면 표시에 쓰는 시간대 |
| `PUBLIC_BASE_URL` | 요청한 호스트 | RSS 속 미디어 절대 URL의 기준 주소 (예: `https://insta.example.com`) |

### 볼륨

| 호스트 | 컨테이너 | 내용 |
|---|---|---|
| `./config` | `/config` | `settings.json`(피드, 옵션, 스케줄), Instagram 세션 파일 |
| `./data` | `/data` | SQLite DB `insta.db` (게시물, 실행 이력) |
| `./downloads` | `/downloads` | 다운로드한 미디어 (`<경로>/<계정>`, `<경로>/hashtag_<태그>`) |

컨테이너는 기본적으로 root로 실행됩니다. Linux 호스트에서 파일 소유권을 맞추려면 `docker-compose.yml`의 `user: "1000:1000"` 주석을 해제하세요.

> ⚠️ `config/`에는 로그인 세션이 들어 있습니다. 외부에 공개하거나 커밋하지 마세요. 저장소의 `.gitignore`에서 이미 제외하고 있습니다.

## 프로젝트 구조

```text
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── CHANGELOG.md
├── .github/workflows/docker.yml   # CI: 빌드 · GHCR 배포 · 릴리스
└── app/
    ├── __init__.py                # __version__ (앱 버전의 기준)
    ├── main.py                    # FastAPI: Web UI, 피드 관리, API, /media, /rss
    ├── instaloader_service.py     # 로그인·세션, 크롤링 로직
    ├── scheduler.py               # APScheduler (interval / cron)
    ├── rss_generator.py           # RSS 2.0 + content:encoded + Media RSS
    ├── db.py                      # SQLite (posts, runs)
    ├── config.py                  # 경로, settings.json, 피드 도우미 함수
    └── templates/                 # Jinja2 + Bootstrap 5 (대시보드, 피드, 설정, 게시물)
```

## 로컬 개발

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`config/`, `data/`, `downloads/`는 현재 디렉터리에 만들어집니다. 경로를 바꾸려면 `CONFIG_DIR`, `DATA_DIR`, `DOWNLOADS_ROOT` 환경 변수를 지정하세요.

## CI/CD

`.github/workflows/docker.yml`이 다음 상황에서 실행됩니다.

| 이벤트 | 동작 |
|---|---|
| Pull Request | 스모크 테스트와 이미지 빌드만 실행 (푸시하지 않음) |
| `main` 브랜치 push | `ghcr.io/jhkim0712/insta_webui:latest`, `sha-<커밋>` 태그로 푸시 |
| `vX.Y.Z` 태그 push | `X.Y.Z`, `X.Y` 태그로 푸시하고 GitHub Release 생성 (릴리스 노트 자동 작성, compose 번들 첨부) |

이미지는 `linux/amd64`와 `linux/arm64`용으로 빌드합니다.

### 릴리스 방법

버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따르고, `app/__init__.py`의 `__version__`을 기준으로 합니다.

1. `app/__init__.py`의 `__version__`을 올립니다 (예: `1.2.0`).
2. `CHANGELOG.md`에 변경 사항을 적습니다.
3. 커밋한 뒤 같은 버전으로 태그를 붙여 push합니다.

```bash
git commit -am "Release v1.2.0"
git tag v1.2.0
git push origin main v1.2.0
```

태그와 `__version__`이 다르면 CI가 실패합니다. 현재 버전은 웹 화면 하단이나 `/healthz` 응답에서 확인할 수 있습니다.

> 첫 이미지를 배포한 뒤 GitHub의 **Packages → insta_webui → Package settings**에서 공개 범위를 **Public**으로 바꿔야 로그인 없이 `docker pull`할 수 있습니다.

## 주의사항

- 수집 주기를 너무 짧게 잡으면 계정이 제한될 수 있습니다. **1시간 이상**을 권장합니다.
- 요청 제한(HTTP 429)에 걸리면 Instaloader가 자동으로 몇 분간 기다립니다. 기다리는 동안에는 중지 버튼이 바로 반영되지 않습니다.
- 인스타그램 이용약관과 콘텐츠 저작권을 지켜서 개인적인 용도로만 사용하세요.
