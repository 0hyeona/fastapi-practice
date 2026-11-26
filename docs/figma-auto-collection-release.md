# Figma 자동 수집 연동 진행 결과 — 2026-11-26 (KST)

## 현재 상태

백엔드 작업 브랜치: `feat/figma-auto-collection` (기준 `develop`, `52e6ab3`).
FE 저장소의 `backend-patches/figma-auto-collection.patch`는 원본 BE에 적용되지 않은 상태였고, `git apply --check` 성공 후 이번 브랜치에 적용했습니다. FE의 `.backend-connection-work`도 확인했습니다. 같은 기능을 새로 개발하지 않았습니다.

운영 DB 변경·새 버전 배포·실제 Figma → FastAPI → TiDB → 운영 FE 검증은 **완료하지 않았습니다**. 로컬 기능 검증과 운영 검증을 혼동하지 마세요.

## 준비된 수정본과 최종 변경의 차이

- 기존 BE에는 pairing/pair/snapshot/status/disconnect만 있었습니다. 수정본의 resume/changes와 수집 상태 필드를 적용했습니다. 기존 API를 유지하며 추가 REST 전체 파일 수집은 만들지 않았습니다.
- 준비된 수정본은 같은 bearer의 만료를 90일씩 연장했습니다. 최종 코드는 최초 인증 후 8시간 절대 만료를 유지하며 자동 연장을 제거했습니다. 별도 refresh credential이 없으므로 만료 후 새 일회용 코드로 연결합니다.
- 인증 만료 상태에서 최근 heartbeat 때문에 수집 중으로 보이는 문제를 막았습니다.
- 연결 코드 재발급 시 마지막 정상 수집 시점을 지우지 않도록 했습니다. 기존 snapshot/활동은 유지합니다.
- 인증된 수신의 실패 원인은 기존 `project_sync_runs`에 비밀정보 없는 코드/메시지로 기록합니다. DB 장애로 이력도 저장할 수 없으면 경고만 남깁니다.
- 기존 `develop`에 커밋된 병합 충돌 표시를 README, external_sync, figma_version_diff, notion_content 및 notion 테스트에서 제거했습니다. 최신 기능이 있는 HEAD 쪽 코드를 보존했습니다. Notion/GitHub의 기능 변경을 새로 추가하지 않았습니다.
- 프로젝트별 기존 단일 인증 연결을 유지합니다. 팀원별 새 연결 테이블을 만들지 않았습니다. 새 연결 코드 발급은 이전 송신기를 무효화합니다. 여러 팀원 편집은 한 실행 중인 플러그인이 수집합니다.

## 수정 파일

| 용도 | 파일 |
| --- | --- |
| API/CORS | `app/routers/figma_plugin.py`, `app/figma_plugin_cors.py` |
| 인증/차이 저장/오류 이력 | `app/services/figma_plugin.py` |
| 상태 모델 | `app/models/figma_plugin.py` |
| 마이그레이션 | `scripts/setup_figma_plugin_db.py`, `sql/figma_plugin.sql`, `sql/migrate_figma_plugin_auto_collection.sql` |
| 기존 충돌 복구 | `app/services/external_sync.py`, `app/services/figma_version_diff.py`, `app/services/notion_content.py`, `tests/test_notion_content.py`, `README.md` |
| 준비된 플러그인 수정본 | `figma-plugin/code.js`, `figma-plugin/ui.html`, `figma-plugin/tests/plugin.test.mjs`, `figma-plugin/README.md` |
| 검증/안내 | `tests/test_figma_plugin_auto.py`, `docs/figma-live-plugin.md`, 이 문서 |

## API 계약

전체 경로·Method·Body·응답 표는 [figma-live-plugin.md](figma-live-plugin.md)에 있습니다. FE의 `src/api/figmaPlugin.ts`와 확인했으며 상태 GET의 필드명이 일치합니다.

새 API는 `POST /api/figma-plugin/resume`, `POST /api/figma-plugin/changes`입니다. snapshot의 성공 응답에 `revision`, `last_sequence`를 추가합니다. 상태 GET/DELETE 응답은 `last_seen_at`, `collection_state`를 추가합니다. 기존 pair 요청과 응답 형식은 유지합니다.

전송별 `sequence`와 현재 snapshot `revision`을 사용해 재전송을 처리합니다. 프로젝트 행 잠금 후 순번/권한을 다시 검사합니다. 순번이 이미 승인된 요청은 활동을 다시 만들지 않으며, 기준 revision이 바뀐 새 배치는 409로 재비교를 요청합니다. 인증정보를 여러 송신기에 복제하는 방식은 지원하지 않습니다. 실제 TiDB 동시성 부하 검증은 남아 있습니다.

## 운영 DB

**실제 적용된 변경: 없음.** DB 검사만 시도했으며 DNS 단계에서 실패했습니다.

| 테이블 | 추가 예정 컬럼 | 타입 | 목적/기존 행 영향 |
| --- | --- | --- | --- |
| `figma_plugin_connections` | `last_seen_at` | `DATETIME NULL` | 마지막 연락 시각. 기존 행은 NULL, offline으로 표시 |
| `figma_plugin_connections` | `collection_state` | `VARCHAR(24) NULL` | collecting/sending/error/paused 상태. 기존 행은 NULL |

기존 프로젝트·사용자·Story·활동·snapshot 행은 수정/초기화하지 않습니다. 기존 plugin 테이블이 있으면 위 두 컬럼만 추가합니다. 기존 테이블이 없을 때만 이미 설계되어 있던 두 plugin 테이블을 생성합니다. 별도 테이블 신설은 없습니다.

적용 전 스키마·행 수를 확인하고, 실제 연결 대상이 운영 `moeum_db`인지 확인하세요. 먼저 `python -m scripts.setup_figma_plugin_db`로 예정 DDL을 검토합니다. 그다음 `--apply`로 적용하고 같은 검사를 재실행합니다. 부분 DDL 실패 후에도 없는 컬럼만 추가하므로 재실행할 수 있습니다. SQLite에서 기존 user/project/story/연결 순번 보존과 반복 적용을 검사했습니다. 운영 TiDB의 타입/권한/DDL 실행 여부는 아직 확인하지 못했습니다.

SQL과 복구 방안: [migrate_figma_plugin_auto_collection.sql](../sql/migrate_figma_plugin_auto_collection.sql). 권장 복구는 컬럼을 남겨 두고 정상 애플리케이션으로 되돌리는 것입니다. 기존 앱은 nullable 컬럼을 무시하므로 불필요한 DROP을 하지 않습니다. 현재 정상 운영 커밋은 Render 조회 당시 `0f0d090`입니다. 충돌 표시가 포함된 `52e6ab3`로 되돌리면 시작할 수 없습니다.

## 오류 확인 결과

| 관찰 | 확인 결과 |
| --- | --- |
| 운영 FastAPI 상태 | 브라우저에서 HTTPS `/docs` 로드 성공 |
| 운영 새 API | Swagger에 resume/changes 없음. 플러그인과 서버의 버전 불일치 확인 |
| Render 최근 배포 | `52e6ab3` 배포 `dep-dc3e77dbedkc73dl73og`는 `update_failed`; `0f0d090`은 `live` |
| 현재 플러그인 API 주소 | `https://fastapi-practice-jwse.onrender.com` |
| manifest 허용 도메인 | 위 HTTPS origin과 일치. FE `figma-plugin-local/manifest.json`도 일치 |
| 로컬 CLI 외부 접근 | GitHub/Render DNS 조회 실패. Git 원격 조회는 `Could not resolve host: github.com` |
| TiDB 검사 | 설정 대상은 TiDB 호스트. `socket.gaierror: [Errno 11001] getaddrinfo failed` |
| Python TLS 초기화 | 주입된 `SSLKEYLOGFILE`이 `aswMonFltProxy` 장치 경로를 가리켜 PermissionError. 테스트 프로세스 내부에서 키 로그 변수만 제거한 뒤 관련 테스트 정상 실행. 인증서 검증/백신/네트워크 보호는 변경하지 않음 |
| 전체 TestClient 테스트 | Windows asyncio `_fallback_socketpair`의 `accept()`에서 대기. faulthandler로 위치 확인 후 중단 |
| Render 런타임 로그 조회 | Render 연결 도구가 503 및 로그 조회 불가 반환. 상세 서버 오류 로그 미확인 |

운영의 새 경로 부재와 그 경로의 iframe CORS 미지원은 새 플러그인의 통신을 막을 수 있습니다. 다만 실제 Figma 요청의 Network 응답을 확보하지 못했으므로 과거 `Failed to fetch`의 단일 원인으로 단정하지 않습니다. 기존 EACCES 또한 실제 발생 스택을 새로 확보하지 못해 원인 확정/해결 완료로 보고하지 않습니다.

CORS는 `null`, `https://www.figma.com` 두 origin과 plugin의 네 POST 경로에만 허용합니다. 일반 로그인 API에 적용하지 않으며 임의 origin/GET은 거부하는 자동 테스트를 통과했습니다. 전체 CORS 허용이나 인증 제거는 하지 않았습니다.

## 검증 범위

| 요청 시나리오 | 로컬 검증 | 운영 실검증 |
| --- | --- | --- |
| 최초 일회용 코드 인증 | SQLite 서비스 테스트 | 미완료 |
| 재실행 자동 연결 | SQLite + 플러그인 VM | 미완료 |
| 텍스트 변경 | 전후 설명/저장 테스트 | 미완료 |
| 프레임 생성·삭제 | 서비스 + VM | 미완료 |
| 색상·크기·위치 | 서비스 + VM | 미완료 |
| 폰트·이름·Auto Layout·컴포넌트 속성 | delta 입력 → 활동 설명 테스트 | 실제 Figma 속성별 이벤트 미확인 |
| 5초 배치 | VM 타이머 테스트 | 미완료 |
| MOEUM 웹 종료 중 전송 | 플러그인이 웹 없이 직접 요청하는 VM | 실제 앱 종료 시나리오 미확인 |
| 동일 배치 재전송 | sequence 중복/활동 개수 검사 | 미완료 |
| 네트워크 오류·응답 유실 재시도 | VM + commit 실패/재전송 | 미완료 |
| 인증 만료·해제·다른 파일/계정 | 서비스 테스트 | 미완료 |
| 재실행 최종 상태 비교 | 서비스 + VM | 미완료 |
| GitHub/Notion 회귀 | 기존 서비스/SQLite 테스트 | 실외부 서비스 재수집 미확인 |
| Story 연결·재조회 | Figma 활동 → 기존 Story 저장 테스트 | 미완료 |
| 운영 TiDB 저장/운영 FE 자동 반영 | 해당 없음 | 미완료 |

검증 결과: 관련 백엔드 테스트 **134개 및 subtest 34개 통과**, 플러그인 Node VM 테스트 **4개 통과**. Python 문법 검사와 `git diff --check`도 수행했습니다. 기존 Figma 관련 테스트를 포함한 수치이며 전체 TestClient 묶음은 위 환경 제약 때문에 완료하지 못했으므로 전체 스위트 통과라고 보고하지 않습니다. FastAPI TestClient/httpx 조합의 기존 deprecation warning이 1개 있습니다.

## FE/플러그인 담당자와 맞출 사항

- FE의 `connected`는 유효한 연결 인증입니다. 실제 실행은 `collection_state`와 `last_seen_at`으로 구분합니다. 플러그인을 닫은 뒤 최대 75초 안에 offline이 됩니다. 저장된 연결과 변경사항은 유지합니다.
- FE는 마지막 수집 시각에 `last_received_at`을 사용합니다. 이번 응답의 추가 필드 때문에 기존 필드를 제거할 필요는 없습니다.
- 8시간 만료 후 새 코드를 받는 안내를 유지하세요. 90일 미사용 만료라는 기존 패치 설명은 폐기했습니다.
- API origin과 manifest는 현재 운영 주소 기준 변경할 필요가 없습니다. 서버 배포 전 새 plugin을 연결해도 resume/changes가 없습니다. 로컬 개발 주소를 쓰려면 허용 도메인과 실제 서버의 실행 가능 여부를 함께 확인해야 합니다.
- BE 저장소의 플러그인 수정본은 업데이트했으나 FE의 `figma-plugin-local` 설치본은 이 작업에서 덮어쓰지 않았습니다. 배포 후 기존 ID를 보존하는 `figma-plugin/install.ps1`로 동기화하세요. 파일 복사만으로 실행 중인 플러그인이 갱신되지는 않으므로 재실행해야 합니다.
- 컴포넌트 속성 delta의 저장은 검증했지만 실제 인스턴스 교체 시 plugin이 `componentId`를 제공하는지는 실파일에서 확인해야 합니다. 모든 Figma 편집 속성/이미지 픽셀을 복원하는 기능은 아닙니다.
- FE 소스의 polling은 약 5초입니다. 운영 FE에 해당 브랜치가 배포되어 있는지, DB 수신 뒤 자동 반영되는지는 아직 확인하지 못했습니다. FE 코드는 이번 BE 작업에서 수정/배포하지 않았습니다.

## 배포 재개 순서

1. 정상 네트워크에서 `git fetch origin` 후 이번 feature 브랜치와 최신 develop 차이를 확인합니다. 작업 브랜치를 보존하세요.
2. 위 DB dry-run → 행 수/스키마 확인 → 마이그레이션 적용 → 재검사를 완료합니다.
3. feature 브랜치를 GitHub에 push하고 Render가 사용하는 `develop`에 반영할 변경을 검토합니다. 서비스의 추적 브랜치는 현재 develop입니다. feature push만으로 운영 배포되지는 않습니다.
4. Render에서 대상 커밋을 배포하고 deploy ID를 기록합니다. `live` 및 `/docs`에 resume/changes가 나타나는지 확인합니다.
5. plugin 설치본을 동기화한 뒤 test 파일에서 첫 연결, 글자 수정, 프레임 생성/삭제, 재시도, 재실행, 만료/해제를 검증합니다.
6. DB 활동·snapshot revision·수집 시각을 확인하고 운영 FE 5초 자동 반영 및 Story 저장을 확인합니다. 인증 토큰/연결 코드를 로그나 보고서에 남기지 마세요.

요청한 커밋 제목: `feat: Figma 플러그인 자동 재연결 및 변경사항 자동 수집 기능 개선`.
