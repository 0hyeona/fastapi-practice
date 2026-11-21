# Starter 파일의 수정사항을 바로 반영하기

기존 Figma REST 수집에서 받은 `429`와 `Retry-After`는 유지합니다. 이 기능은 Figma 편집기에서 플러그인 API로 읽은 내용을 모음 서버에 직접 전송합니다. 모음에서 새로고침할 때 Figma REST API를 다시 호출하지 않습니다.

실시간 연결을 사용하려면 아래의 **코드 적용, DB 준비, 두 서비스 배포, 플러그인 설치**가 모두 필요합니다. 파일을 준비한 것만으로 운영 사이트가 바뀌지는 않습니다.

## 1. 실제 백엔드와 프론트 폴더에 적용

PowerShell에서 다음을 실행합니다.

```powershell
& "C:\Users\rhwld\OneDrive\문서\ChatGPT\모음-백엔드\fastapi-practice\apply-figma-live.ps1"
```

이 스크립트는 지정한 백엔드 `fastapi-practice`와 프론트 `moeum`에 이번 기능의 파일만 복사합니다. 준비 이후 대상 파일이 바뀌었다면 중단하여 수정 중인 내용을 덮어쓰지 않습니다. Git commit/push와 배포는 자동 실행하지 않습니다.

두 저장소에서 각각 `git status --short`로 변경사항을 확인하세요. 기존의 다른 수정사항이나 `moeum-github-visitors.patch`를 한꺼번에 stage하지 않아도 됩니다.

## 2. DB에 두 테이블 준비

실제 백엔드 폴더에서 실행합니다. 이 명령은 기존 `.env`의 DB에 **새 테이블 두 개만** 생성하며, 기존 인증 정보와 활동은 보존합니다.

```powershell
Set-Location -LiteralPath "C:\Users\rhwld\OneDrive\바탕 화면\휴학\fastapi-practice"
.\.venv\Scripts\python.exe -m scripts.setup_figma_plugin_db --apply
```

직접 SQL을 실행하려면 `sql/figma_plugin.sql` 전체를 TiDB에서 실행해도 됩니다. 이 SQL의 DB 이름은 현재 사용 중인 `moeum_db`입니다. 두 방법 중 하나만 사용하면 됩니다.

| 테이블 | 저장하는 내용 |
| --- | --- |
| `figma_plugin_connections` | 소유자와 프로젝트·파일에 묶인 연결 코드/세션의 해시, 만료 시각, 마지막 전송 순서 |
| `project_figma_snapshots` | 해당 프로젝트 파일의 마지막 전체 상태와 비교 순번 |

## 3. 백엔드와 프론트를 각각 배포

수정 파일은 다음 목록으로 확인하고 stage할 수 있습니다.

```powershell
# 백엔드 develop 저장소에서
$backendFiles = Get-Content -LiteralPath .\figma-live-backend-files.txt -Encoding UTF8
git add -- $backendFiles
git diff --cached --stat
# 확인 후 기존 방식으로 commit/push하고 Render 배포 완료를 확인합니다.

# 프론트 main 저장소에서
Set-Location -LiteralPath "C:\Users\rhwld\OneDrive\바탕 화면\휴학\moeum"
$frontendFiles = Get-Content -LiteralPath .\figma-live-frontend-files.txt -Encoding UTF8
git add -- $frontendFiles
git diff --cached --stat
# 확인 후 기존 방식으로 commit/push하고 Vercel 배포 완료를 확인합니다.
```

추가 환경변수는 필요하지 않습니다. 기존 `FRONTEND_ORIGINS`는 그대로 사용하고, 플러그인 iframe의 CORS는 `/api/figma-plugin/pair`, `/api/figma-plugin/snapshot` 두 경로에만 별도 적용합니다.

## 4. Figma Desktop에 플러그인 설치 (최초 한 번)

개발용 플러그인은 **Figma Desktop 앱**에서 실행해야 합니다.

1. Figma Desktop에서 대상 디자인 파일을 엽니다.
2. 메뉴 **Plugins → Development → New plugin**을 선택합니다.
3. **Figma design**, 이름 **모음 실시간 연결**, **Custom UI**를 선택하고 새 폴더에 저장합니다. Figma가 `manifest.json`에 실제 플러그인 ID를 발급합니다.
4. 아래 명령의 `Destination`을 방금 저장한 **manifest.json이 있는 폴더**로 바꿔 실행합니다.

```powershell
& "C:\Users\rhwld\OneDrive\바탕 화면\휴학\fastapi-practice\figma-plugin\install.ps1" `
  -Destination "C:\Users\rhwld\Desktop\moeum-live-plugin"
```

설치 스크립트는 Figma가 발급한 ID를 보존하고 `code.js`, `ui.html`, 필요한 manifest 설정을 넣습니다. 제공된 manifest는 설정 템플릿이므로 ID 없이 직접 가져오지 마세요. npm 설치나 빌드는 필요하지 않습니다.

5. Figma Desktop에서 **Plugins → Development → 모음 실시간 연결**을 실행합니다. 처음 만든 템플릿 화면이 남아 있다면 플러그인을 닫고 다시 실행합니다.

## 5. 프로젝트와 연결하고 실제 수정 확인

1. 모음 대시보드의 **Figma → 플러그인으로 실시간 연결 → 연결 코드 만들기**를 누릅니다. 프로젝트 소유자만 코드를 만들 수 있습니다.
2. Figma 플러그인에 **연결 코드**와 **지금 열린 파일의 공유 링크**를 붙여 넣고 **연결하고 기준 저장**을 누릅니다.
3. 플러그인에 **기준 저장 완료**가 나오는지 확인합니다. 기존 미정리 16개가 있다면 그대로 유지하며, 최초 기준 전송으로 개수를 추가하지 않습니다.
4. Figma의 텍스트 한 개를 `연동 확인 A`에서 `연동 확인 B`로 바꿉니다.
5. 플러그인에서 **전송 완료 · 변경사항 1개 추가**를 확인합니다. 입력을 멈춘 뒤 약 1초의 묶음 처리와 서버 통신 시간이 필요합니다.
6. 모음의 **새로고침**을 누릅니다. 기존 개수에서 1 증가하고, 변경사항에 `연동 확인 A → 연동 확인 B`가 나타나면 정상입니다.
7. Figma를 수정하지 않고 한 번 더 새로고침하거나 **지금 보내기**를 눌러도 개수는 늘어나지 않아야 합니다.

플러그인을 켜둔 동안만 편집을 보냅니다. 창을 닫거나 8시간이 지나면 모음에서 새 연결 코드를 만들어 다시 연결하세요. 코드 하나는 10분 동안 한 번만 사용할 수 있고 새 코드를 만들면 이전 플러그인 세션이 해제됩니다. 연결 해제도 모음 화면에서 할 수 있습니다.

## 동작 범위와 확인할 점

- 텍스트, 부분 텍스트 스타일, 채우기·테두리, 크기·위치, 일부 배치 속성, 요소 추가·삭제·순서를 비교합니다. 이미지 픽셀, 벡터 경로 자체, 댓글, 모든 Figma 속성을 수집하는 기능은 아닙니다.
- 약 1초 동안의 여러 편집은 **활동 1개**로 묶습니다. 모음의 개수는 활동 개수이고, 활동 설명 안에 요소별 추가·삭제·수정 수와 비교 내용이 표시됩니다. 전송 전에 실행하고 취소하여 최종 상태가 같으면 새 활동을 만들지 않습니다.
- 처음 보내기 전의 변경 내역이나 플러그인을 닫은 동안의 개별 편집 과정은 복원하지 않습니다. 다시 연결할 때 마지막으로 저장한 상태와 현재 상태의 차이를 비교합니다.
- 일반 플러그인은 현재 파일 키를 자동으로 읽을 수 없어 공유 링크를 직접 입력합니다. 서버는 그 링크가 프로젝트에 등록한 파일인지 확인하지만, **편집기에서 실제로 그 파일을 열었는지**는 사용자가 확인해야 합니다.
- 전체 파일의 모든 페이지를 읽습니다. 큰 스냅샷은 gzip으로 압축한 뒤 보냅니다. 압축 전 요청은 32 MiB, 전송 본문은 4 MiB, 정규화한 비교 데이터는 48 MiB까지 지원하며 저장용 압축 JSON은 4 MiB 이내여야 합니다. 요소 수 한도는 100,000개입니다. 초과하면 기존 기준과 변경 기록을 유지합니다. 백엔드를 먼저 배포한 뒤 플러그인을 업데이트하세요. 기존 테이블과 이전 플러그인의 JSON 전송도 지원합니다.
- 현재 플러그인은 `https://fastapi-practice-jwse.onrender.com`으로만 전송합니다. 백엔드 주소가 바뀌면 `ui.html`의 `API`와 `manifest.json`의 `networkAccess.allowedDomains`를 함께 바꾼 뒤 설치 스크립트를 다시 실행하세요.
- 브라우저 F5는 서버에 이미 저장된 최신 목록을 읽습니다. Figma 카드의 새로고침은 플러그인 모드에서 저장된 최신 목록을 다시 조회하며, 기존 REST 한도를 소비하지 않습니다.
- 기존 REST 실패 기록을 삭제하거나 만료 시간을 임의로 바꾸지 않아도 플러그인 모드는 동작합니다. REST 수집으로 돌아가려면 **실시간 연결 해제**를 누르며, 그때는 실제 Figma REST 대기 시간이 적용됩니다.

서버 저장 여부는 다음으로 확인할 수 있습니다. 인증 토큰/연결 코드를 조회할 필요는 없습니다.

```sql
SELECT project_id, enabled, expires_at, last_sequence, last_received_at
FROM moeum_db.figma_plugin_connections
WHERE project_id = 150001;

SELECT id, title, description, occurred_at
FROM moeum_db.project_activities
WHERE project_id = 150001 AND source = 'figma'
ORDER BY id DESC LIMIT 5;
```

## 검증

백엔드 SQLite 테스트에서 소유자 권한, 코드 만료·일회성, 파일 일치, 세션 해제, 실제 REST 429와의 독립성, 중복·순서 역전, 변경 비교, 실패 시 원본 보존을 확인합니다. 플러그인 JavaScript 테스트는 페이지 로딩·편집 감지·전송 직렬화·재시도를 확인합니다. 프론트 타입 검사와 프로덕션 빌드도 확인합니다.

운영 Render/TiDB에 배포하거나 실제 Figma Desktop에서 실행한 것은 아니므로, 위 5단계의 실제 전송 확인이 마지막 검증입니다.

참고한 공식 문서:

- https://developers.figma.com/docs/rest-api/rate-limits/
- https://developers.figma.com/docs/plugins/plugin-quickstart-guide/
- https://developers.figma.com/docs/plugins/api/figma/
- https://developers.figma.com/docs/plugins/manifest/
