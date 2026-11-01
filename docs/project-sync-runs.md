# 수집 실행 이력

기존 테이블과 데이터를 유지하고 `project_sync_runs`만 추가합니다. 배포 전에 기존 앱 DB에 마이그레이션을 적용하세요.

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_sync_runs_db
.\.venv\Scripts\python.exe -m scripts.setup_sync_runs_db --apply
```

TiDB SQL 편집기에서는 앱 DB를 선택한 뒤 `sql/project_sync_runs.sql`을 실행할 수도 있습니다. 이 변경은 과거 수집 이력을 복원하지 않습니다.

## 기록 범위

GitHub, Figma, Notion의 기존 POST 수집 API 및 실제 실행되는 Figma·Notion 최초 수집 작업에 공통으로 적용됩니다. 읽기 전용 GET, 인증/요청 검증에서 거절된 요청, 설정 부족으로 건너뛴 백그라운드 작업은 기록하지 않습니다. 페이지 단위 요청마다 이력 1개가 생기며, 기존 수집 응답 형식은 유지됩니다.

- `project_id`, `source`: 프로젝트와 서비스
- `started_at`, `finished_at`: UTC 기준 시작/종료 시각
- `status`: `running`, `success`, `failed`
- `fetched`, `created`, `existing`: 조회/신규 저장/중복 개수
- `error_code`, `error_message`: 실패 상태 코드와 안전한 오류 분류. 토큰이나 외부 오류 원문은 저장하지 않습니다.

실패하면 해당 실행의 활동 저장을 롤백하고 `created=0`으로 기록합니다. 조회 단계가 끝났을 때만 `fetched`에 조회 개수를 남기며 실패 시 `existing`은 0입니다. 프로세스 강제 종료나 DB 장애로 종료 기록을 저장하지 못하면 `running`이 남을 수 있습니다. 이는 성공을 뜻하지 않습니다.

## Swagger 확인

로그인 후 본인 프로젝트의 수집 API를 실행하고 아래 조회를 확인합니다.

```text
GET /api/projects/1/sync-runs
GET /api/projects/1/sync-runs?source=figma
GET /api/projects/1/sync-runs?source=notion&status=failed&limit=1
GET /api/projects/1/sync-runs?source=github&status=success&limit=1
```

최신 시작 시각 및 ID 순으로 반환합니다. `limit` 기본값은 50, 최대 100이며 `offset`으로 페이지를 이동합니다. `status`와 `source`를 조합하고 `limit=1`로 서비스별 마지막 성공/실패 이력을 조회할 수 있습니다. 이력이 없으면 빈 배열입니다. 다른 사용자 소유 프로젝트는 기존 소유권 검증으로 차단됩니다.

주기적 스케줄러, Render 배포, 실제 외부 계정 수집 검증은 이 변경에 포함되지 않습니다.
