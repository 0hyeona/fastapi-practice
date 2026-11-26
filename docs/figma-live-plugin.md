# Figma 자동 수집 API 적용 안내

플러그인 최초 일회 연결 후 기기 저장소의 프로젝트·파일 전용 토큰으로 자동 재연결합니다. 신규 수집 경로는 Figma REST API를 호출하지 않습니다.

## DB 준비

기존 `figma_plugin_connections`에 nullable 컬럼 `last_seen_at DATETIME`, `collection_state VARCHAR(24)`를 추가합니다. 기존 `project_figma_snapshots`와 `project_activities`를 그대로 사용하며 데이터를 삭제/초기화하지 않습니다.

운영 DB 환경변수가 설정된 백엔드에서 실행하세요:

```powershell
python -m scripts.setup_figma_plugin_db
python -m scripts.setup_figma_plugin_db --apply
```

첫 명령은 검사만 합니다. `--apply`는 필요한 컬럼만 추가하고 반복 실행 가능합니다. 플러그인 테이블이 아예 없으면 기존 두 테이블을 생성합니다. 이미 테이블이 있는 환경에는 CREATE TABLE SQL만 재실행해서는 새 컬럼이 생기지 않습니다.

## API

- 기존 pairing/pair/snapshot/상태 GET/연결 DELETE는 유지합니다.
- `POST /api/figma-plugin/resume`: bearer 토큰과 `{file_url, state}`. 계정·프로젝트 소유자·파일·만료·해제를 검증하고 `last_sequence`, `revision`, 프로젝트 이름, 만료 시각을 반환합니다.
- `POST /api/figma-plugin/changes`: `{sequence, file_url, name, base_revision, upserts, deleted}`. upserts는 children에 자식 ID 배열을 갖는 변경 노드입니다. 부모 구조 변경과 생성된 하위 트리를 함께 보냅니다.
- snapshot 응답에도 `revision`, `last_sequence`를 추가합니다. 기존 JSON/gzip 요청은 호환됩니다.
- 상태 GET에는 `last_seen_at`, `collection_state`를 추가합니다. 75초간 heartbeat가 없으면 offline을 반환합니다.
- iframe CORS는 pair/snapshot/resume/changes 네 경로에만 적용합니다.

토큰은 해시로 저장하고 소유자/프로젝트/파일에 제한합니다. 최초 발급 후 **8시간 절대 만료**를 유지하며 resume·heartbeat·전송으로 만료를 연장하지 않습니다. 별도 회전 가능한 refresh credential이 없으므로 기존 bearer만으로 안전한 장기 갱신을 제공하지 않습니다. 만료 시 401을 반환하고 플러그인은 새 연결 코드 입력을 안내합니다. 일회용 코드는 10분 동안 한 번만 사용하며 새 코드 발급과 연결 해제는 이전 토큰을 무효화합니다.

변경 배치는 기존 비교 기준 revision을 확인한 후 트리 전체의 구조를 검증합니다. revision 충돌이나 누락/순환 구조는 409이며 플러그인은 전체 최종 상태를 다시 보냅니다. 이미 승인한 sequence는 중복 저장하지 않습니다. DB commit 실패는 기준과 활동을 함께 롤백합니다.

정상 저장 시각은 `last_received_at`, 플러그인의 최근 연락은 `last_seen_at`입니다. 인증이 만료되거나 75초간 연락이 없으면 `collection_state=offline`입니다. 연결 코드 재발급은 마지막 성공 시각과 기존 snapshot/활동을 지우지 않습니다. 인증된 수신 중 발생한 구조·저장 오류는 기존 `project_sync_runs`에 `Figma plugin:` 접두어와 안전한 원인·HTTP 코드로 기록합니다. `GET /api/projects/{project_id}/sync-runs?source=figma`로 확인할 수 있습니다. DB 자체가 연결 불가능하면 이력 기록도 불가능하며 서버에 비밀정보 없는 경고를 남깁니다. 수신 전 JSON/gzip 형식 오류는 HTTP 응답으로 확인합니다.

### 정확한 계약

플러그인 요청은 JSON 또는 snapshot/changes에 한해 `application/gzip`으로 압축한 JSON입니다. pair 이외의 플러그인 요청은 `Authorization: Bearer moeum_figma_plugin_...`를 사용합니다. 프로젝트 경로의 GET/POST/DELETE는 MOEUM 로그인 bearer를 사용합니다. 모든 응답에 `Cache-Control: no-store`가 적용됩니다.

| Method | 전체 경로 | Body | 성공 응답 |
| --- | --- | --- | --- |
| POST | `/api/projects/{project_id}/figma/plugin/pairing` | 없음 | `{code, expires_at, project_name, file_url}` |
| POST | `/api/figma-plugin/pair` | `{code, file_url}` | `{token, expires_at, project_id, project_name, file_url}` |
| POST | `/api/figma-plugin/resume` | `{file_url, state}` (`collecting/sending/error/paused`) | `{project_id, project_name, last_sequence, revision, expires_at}` |
| POST | `/api/figma-plugin/snapshot` | `{sequence, file_url, name, document}` | `{created, baseline, duplicate, received_at, revision, last_sequence}` |
| POST | `/api/figma-plugin/changes` | `{sequence, file_url, name, base_revision, upserts, deleted}` | snapshot과 동일 |
| GET | `/api/projects/{project_id}/figma/plugin` | 없음 | `{enabled, connected, expires_at, last_received_at, last_seen_at, collection_state}` |
| DELETE | `/api/projects/{project_id}/figma/plugin` | 없음 | 상태 GET과 동일 |

`created`는 0 또는 1입니다. 한 배치의 여러 노드 변경을 기존 Figma 활동 한 개에 요약합니다. 처음 기준만 저장할 때 `baseline=true`이고 활동은 생성하지 않습니다. 실패는 `{detail: ...}`와 HTTP 401/409/413/422/500 등으로 반환하며 저장 성공을 가장하지 않습니다.

## 플러그인/프론트

백엔드와 DB를 먼저 배포한 뒤 플러그인을 업데이트하세요. `figma-plugin/install.ps1`은 기존 발급 ID를 보존합니다. 기기 저장소에는 토큰·URL·순번·revision과 작은 실패 배치를 저장하고, 큰 배치는 재실행 시 현재 파일의 전체 최종 상태로 보완합니다. 토큰은 Figma 문서 데이터에 넣지 않습니다.

시작할 때 전체 페이지를 한 번 읽습니다. 실행 중에는 documentchange를 모아 약 5초마다 변경 노드만 전송합니다. 네트워크 오류는 같은 배치를 1~30초 지수 지연으로 재시도합니다. 웹사이트가 닫혀도 플러그인이 직접 서버에 전송합니다. 웹은 DB 목록을 약 5초마다 읽으며 Figma REST 전체 파일 조회를 실행하지 않습니다.

플러그인 종료 중의 모든 중간 편집은 복원할 수 없습니다. fileKey가 일반 플러그인에 제공되지 않는 경우, 입력 URL과 실제 열린 파일의 동일성을 강하게 증명할 수 없으므로 공유 링크를 확인하세요. 기존 프로젝트당 단일 연결 구조를 유지합니다. 여러 팀원이 Figma에서 편집해도 수집 담당 플러그인 한 개가 문서 변경을 수신합니다. 다른 기기에서 새 코드를 사용하면 기존 기기의 인증은 무효화됩니다. 각 팀원별 독립 송신 세션은 제공하지 않으며 동일 bearer 복사는 지원하지 않습니다. 프로젝트 잠금과 revision 검사로 동시 쓰기를 직렬화하고 오래된 배치는 최종 상태 재비교로 보완합니다.

## 검증/상태

SQLite 테스트에서 텍스트·색상·크기·생성·삭제, 중복, 실패 후 재전송, 재실행 최종 상태 보완, 소유자·계정·파일 권한, 만료·해제, nullable 컬럼 마이그레이션을 확인합니다. VM 결합 테스트에서 기기 저장소, 자동 재연결, 5초 배치, gzip, 네트워크와 응답 유실 재시도를 검증합니다.

진행 결과와 운영 배포 재개 절차는 [figma-auto-collection-release.md](figma-auto-collection-release.md)를 확인하세요. 운영 DB용 ALTER 및 복구 안내는 [migrate_figma_plugin_auto_collection.sql](../sql/migrate_figma_plugin_auto_collection.sql)에 있습니다. 코드/SQLite/VM 테스트와 실제 운영 전송 검증은 별개입니다.
