# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [1.1.0] - 2026-09-24

### Added
- **여러 피드 관리**: 피드마다 이름을 붙이고 계정·해시태그를 묶어 등록합니다. 피드별 RSS 주소는 `/rss/feed/<id>`입니다.
- 피드 화면: 만들기, 편집, 삭제, 자동 수집 켜기/끄기, **이 피드만 실행**
- 게시물 화면에서 피드별로 걸러 보기
- 화면 하단과 `/healthz` 응답에 앱 버전 표시

### Changed
- 수집 대상 입력을 설정 화면에서 피드 화면으로 옮겼습니다. 다운로드 옵션, 스케줄, 저장 경로는 모든 피드에 공통으로 적용됩니다.
- 여러 피드에 들어 있는 같은 대상은 한 번만 수집합니다.

### Migration
- 이전 버전 `settings.json`의 `profiles`/`hashtags`는 처음 실행할 때 **기본 피드**로 자동으로 옮겨집니다. 따로 할 일은 없습니다.

## [1.0.0] - 2026-09-24

### Added
- Instaloader 기반 계정·해시태그 수집, 로그인과 세션 파일 업로드 (2단계 인증 지원)
- Web UI: 대시보드, 설정, 게시물 갤러리
- APScheduler 스케줄링 (주기 / Cron), 지금 실행, 중지
- RSS 2.0 피드 (`content:encoded` 안의 이미지·동영상, Media RSS)
- Docker 이미지와 GitHub Actions 빌드·GHCR 배포·릴리스

[1.1.0]: https://github.com/jhkim0712/insta_webUI/releases/tag/v1.1.0
[1.0.0]: https://github.com/jhkim0712/insta_webUI/commit/c6f70ad
