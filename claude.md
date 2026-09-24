# Project Overview: Instaloader Web UI & RSS Service (Dockerized)

이 프로젝트는 **Instaloader**를 기반으로 인스타그램 데이터를 수집하고, 이를 관리할 수 있는 Web UI 및 수집된 콘텐츠를 RSS 피드로 제공하는 컨테이너 기반(Docker) 애플리케이션 구축 프로젝트입니다.

---

## 1. Core Requirements (핵심 요구사항)

1. **Docker 기반 실행 환경 제공**
   - 단일 명령어(`docker compose up -d`)로 전체 서비스를 실행할 수 있어야 합니다.
   - 데이터 보존을 위해 볼륨 매핑(설정, 다운로드 미디어, DB)이 적용되어야 합니다.

2. **Web UI 기능**
   - **Instaloader 파라미터 설정**: 타겟 계정(Account), 해시태그(Hashtag), 다운로드 옵션(사진/동영상/댓글 포함 여부 등) 입력/관리.
   - **스케줄링 설정**: 크롤링 주기(예: 매 1시간, 매일 midnight, Cron 표현식 등) 설정 및 즉시 실행(Run Now) 버튼 제공.
   - **다운로드 경로 지정**: 크롤링한 미디어를 지정한 Host/Container 내부 특정 경로(`/downloads/...`)에 저장 가능하도록 설정.

3. **RSS Feed 서비스 제공**
   - 크롤링한 인스타그램 게시물의 **이미지/비디오 media 및 캡션(내용)**을 포함하는 RSS 피드 URL 생성 및 제공.
   - RSS 뷰어/리더 애플리케이션에서 올바르게 인라인 이미지를 랜더링할 수 있어야 함.

---

## 2. Technical Stack Recommendation (추천 기술 스택)

- **Language & Core Engine**: Python 3.11+, `instaloader`
- **Web Framework / API**: FastAPI 또는 Flask (RSS XML 생성 및 REST API용)
- **Task Scheduling**: APScheduler 또는 Celery + Redis
- **Frontend (Web UI)**: React / Vue.js 또는 Python Jinja2 Template + HTMX / Bootstrap (경량화 선택 가능)
- **Containerization**: Docker, Docker Compose

---

## 3. Recommended Architecture & Directory Structure

```text
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── config/             # 사용자 설정 저장 (JSON 또는 SQLite)
├── data/               # SQLite 데이터베이스 (수집 이력 및 RSS 데이터 관리)
├── downloads/          # 인스타그램 미디어 다운로드 폴더 (볼륨 바인딩)
└── app/
    ├── main.py         # Web Server 및 API 엔드포인트
    ├── instaloader_service.py # Instaloader 연동 logic
    ├── scheduler.py    # 크롤링 주기 관리 (APScheduler 등)
    ├── rss_generator.py # RSS 2.0 XML 생성 logic
    └── templates/      # Web UI 템플릿