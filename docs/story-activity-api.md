# Story / Project Activities API

모든 요청은 Authorization: Bearer <token> 인증과 프로젝트 소유권 검사를 거칩니다.

| Method | 경로 | 기능 |
| --- | --- | --- |
| POST / GET | /stories | Story 생성 / 목록 |
| GET / PATCH / DELETE | /stories/{story_id} | Story 상세 / 수정 / 삭제 |
| POST / GET | /project_activities | 활동 등록 / 목록 |
| GET / PATCH / DELETE | /project_activities/{activity_id} | 활동 상세 / 수정 / 삭제 |
| GET | /api/projects/{project_id}/stories | 프로젝트 Story 목록 |
| GET | /api/projects/{project_id}/activities | 프로젝트 활동 목록 |

기존 목록 API는 project_id, limit(1~100), offset으로 필터링합니다.
Story는 story_status(draft/published), 활동은 source(github/figma/notion)를 지원합니다.
활동 목록의 unorganized=true는 story_id가 null인 활동만, false는 연결된 활동만 반환합니다.
생략하면 전체 활동을 반환합니다. 목록 응답은 JSON 배열입니다.

## Story

POST /stories 예시:

```json
{"project_id":1,"title":"로그인 개선","content":"작업 기록","story_status":"draft"}
```

API의 story_status는 DB의 status 컬럼에 매핑됩니다.
응답에는 id, project_id, title, content, story_status, created_at, updated_at이 있습니다.
목록은 created_at, id 내림차순입니다.

## 활동

POST /project_activities 예시:

```json
{"project_id":1,"source":"github","activity_type":"commit","title":"로그인 개선","occurred_at":"2026-11-01T00:00:00Z"}
```

선택 입력은 description, source_url, story_id입니다. occurred_at에는 시간대가 필요하며 UTC로 저장합니다.
응답 식별자는 activity_id이며 DB 컬럼은 id입니다.
응답에 story_id, external_id, branch_name, created_at을 포함하며 updated_at은 사용하지 않습니다.
external_id와 branch_name은 동기화에서 관리하므로 수동 등록/수정 입력에는 없습니다.
활동 목록은 occurred_at, id 내림차순입니다.

PATCH /project_activities/{activity_id}의 {"story_id": 3}은 같은 프로젝트의 Story에 연결합니다.
{"story_id": null}은 연결을 해제합니다. 다른 프로젝트의 Story는 연결할 수 없습니다.
Story 삭제 시 활동은 유지되고 story_id가 null이 됩니다.
프로젝트 삭제 시 관련 Story와 활동은 삭제됩니다.
수집한 활동의 source 변경은 금지합니다. 삭제한 커밋 활동은 다음 동기화에서 다시 수집될 수 있습니다.

## DB 및 외부 수집

새 DB의 테이블 생성은 sql/schema.sql, 기존 테이블 점검은 scripts/setup_dashboard_db.py를 사용합니다.
CREATE TABLE IF NOT EXISTS는 이미 있는 테이블의 구조를 변경하지 않습니다.
GitHub 커밋 수집은 POST /api/projects/{project_id}/github/sync를 명시적으로 호출합니다.
Figma/Notion 자동 수집, 주기적 스케줄러, 웹훅은 포함하지 않습니다.
Swagger 사용 순서와 DB 적용 명령은 [github-dashboard-api.md](github-dashboard-api.md)를 참고하세요.
