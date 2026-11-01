# 프로젝트 연결 정보 API

현재 프로젝트는 서비스별 URL을 하나씩 저장합니다. projects.github_url / notion_url / figma_url을 단일 저장소로 유지하며 project_connections 테이블은 추가하지 않습니다.
외부 ID는 URL에서 파싱합니다. 서비스별 여러 리소스, 사용자별 OAuth, 수집 실행 이력까지 관리하려면 별도 연결/실행 테이블 설계가 필요합니다.

| Method | API | 기능 |
| --- | --- | --- |
| GET | /api/projects/{project_id} | 프로젝트 상세 (기존 /projects/{project_id}도 유지) |
| GET | /api/projects/{project_id}/connections | github/notion/figma의 링크·ID·설정 상태·미정리 개수 |
| PATCH | /api/projects/{project_id}/connections/{source} | 한 서비스 링크 등록/교체/해제 |
| GET | /api/projects/{project_id}/activities?source=github | GitHub 활동 |
| GET | /api/projects/{project_id}/activities?source=notion | Notion 활동 |
| GET | /api/projects/{project_id}/activities?source=figma | Figma 활동 |
| GET | /api/projects/{project_id}/dashboard | 요약 |

모든 경로는 로그인과 프로젝트 소유권을 검사합니다. source 생략 시 모든 서비스 활동을 반환합니다.
unorganized=true를 추가하면 Story에 연결되지 않은 활동만 조회합니다.

PATCH 예시 (source=figma):

```json
{"external_url":"https://www.figma.com/design/FILEKEY/NAME"}
```

해제는 {"external_url":null}. 빈 요청은 거절합니다. 다른 서비스 형식의 URL도 거절합니다.
연결 해제/교체 시 기존 활동은 삭제하지 않습니다. 미정리 개수는 이전 연결의 기록을 포함한 프로젝트의 모든 해당 source 활동을 집계합니다.
프로젝트 생성/수정 API의 github_url, notion_url, figma_url 입력도 계속 지원합니다.
Figma/Notion은 인증이 설정되어 있으면 링크 저장 후 최초 백그라운드 수집을 시도합니다.
GitHub는 POST /api/projects/{project_id}/github/sync 호출로 수집합니다.

connections 응답은 project_id와 connections 배열이며 항상 GitHub, Notion, Figma 세 항목을 제공합니다.
각 항목: source, external_id, external_url, connection_status, access_verified, detail, unorganized_count, last_activity_stored_at.

- not_linked: URL 없음
- invalid_url: 기존 URL 형식 오류
- configuration_required: Figma/Notion 토큰 또는 허용 대상 설정 필요
- configured: 서버 인증 설정 있음 (실제 외부 접근 성공을 의미하지 않음)
- public_access_unverified: GitHub 토큰 없이 공개 저장소 조회 모드

조회 API는 외부 API를 호출하지 않으므로 access_verified는 false입니다.
last_activity_stored_at은 해당 source 활동의 가장 최근 DB 생성 시각이며, 마지막 수집 성공 시각이 아닙니다.
빈 수집/중복 수집/실패 이력을 별도로 기록하지 않습니다. 수집 결과는 POST sync의 응답으로 확인합니다.
실제 연결 검증, 인증 설정, 수집 범위는 figma-notion-sync.md와 github-dashboard-api.md를 참고하세요.
