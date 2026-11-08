# Notion 본문 변경 수집

배포 전에 `project_notion_snapshots` 테이블이 필요합니다. 사용자가 실행한 SQL과
모델의 필드(`id`, `project_id`, `resource_id`, `revision`, `content`)가 일치합니다.
추가 환경변수나 활동 테이블 변경은 없습니다.

기존 Notion 수집 API와 초기 수집에서 동일한 수집기를 사용합니다.
첫 성공 수집은 페이지별 비교 기준만 저장하며 활동은 생성하지 않습니다.
다음 수집부터 블록 ID 기준으로 본문과 제목을 비교합니다.
수정 시각만 달라졌거나 본문이 같으면 활동 및 revision을 변경하지 않습니다.

| activity_type | description |
| --- | --- |
| title_changed | 수정 전: 이전 제목 / 수정 후: 새 제목 |
| content_updated | 수정 전: 이전 본문 / 수정 후: 새 본문 |
| content_added | 추가된 내용: 본문 |
| content_deleted | 삭제된 내용: 본문 |

각 변경을 별도 `project_activities` 행으로 저장합니다. `source=notion`이며
기존 활동 조회 API의 `title`, `description`, `activity_type`으로 표시할 수 있습니다.
`description`은 JSON이 아닌 일반 문자열입니다. 수정 전·후는 줄바꿈으로 구분합니다.
API 문자열은 프론트에서 HTML로 해석하지 않고 텍스트로 렌더링해야 합니다.
수집 응답의 `fetched`, `created`는 감지한 변경 기록 수이며 첫 수집/무변경은 0입니다.
`existing=0`, `has_next=false`, `next_cursor=null`입니다.

본문 페이지네이션과 중첩 블록을 내부에서 수집합니다. 문단, 제목 블록, 목록,
할 일(체크 상태 포함), 표 행, 캡션 및 하위 페이지/DB 제목을 비교합니다.
별도 하위 페이지와 데이터베이스 내부, 서식만의 변경, 블록 이동,
이미지 바이너리 및 댓글은 비교하지 않습니다.
200회 본문 요청 또는 중첩 깊이 50 초과는 부분 저장하지 않고 실패 처리합니다.

수집 전 프로젝트 잠금을 획득해 동일 프로젝트 수집을 직렬화합니다.
수집 전후 페이지 제목/수정 시각이 다르면 409로 실패하며 재시도가 필요합니다.
외부 오류, 잘못된 응답, 페이지네이션 실패 또는 DB 저장 실패 시 변경 활동과
스냅샷을 함께 롤백하고 수집 실패 이력을 남깁니다.

실제 편집 이력 전체가 아니라 두 성공 수집 시점 사이의 차이입니다.
기존 활동에서 과거 본문을 복원하지 않으며 기존 Story 연결은 유지합니다.

검증 순서: 첫 수집(created=0) → Notion 본문/제목 수정 → 재수집 →
활동 조회에서 전후 확인 → 변경 없이 재수집(created=0).
로컬 테스트는 SQLite와 모의 Notion 응답을 사용합니다.

공식 API: https://developers.notion.com/reference/get-block-children
