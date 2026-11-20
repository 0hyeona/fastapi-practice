# Notion 연결 승인 화면 적용

이 패치는 현재 moeum 프론트 소스를 기준으로 준비했습니다. 원래 프론트 폴더에는 적용하지 않았습니다.

## 추가한 화면

- 프로젝트 설정의 Notion 계정 연결 / 페이지 권한 다시 연결 버튼
- `/auth/notion/callback` 콜백 화면: 승인 코드 교환, 승인 취소·오류 안내, 설정으로 복귀
- 대시보드와 변경사항 목록의 Notion 오류에서 연결 설정으로 이동하는 링크
- 로그인 인증, 같은 창의 state 확인, React StrictMode 중복 교환 방지

사용자 흐름: 프로젝트 설정 → Notion 계정 연결 → 계정·페이지 승인 → 프로젝트 설정 복귀 → 승인한 페이지 URL 저장 → 새로고침 시 변경사항 수집.

## 프론트에 적용

프론트 프로젝트 폴더의 터미널에서 실행합니다. `--check`가 실패하면 적용하지 말고 변경된 프론트와 패치를 다시 비교하세요.

```powershell
git apply --check "C:/Users/ouskx/IdeaProjects/fastapi-practice/fastapi-practice/frontend-integration/notion-oauth/frontend.patch"
git apply "C:/Users/ouskx/IdeaProjects/fastapi-practice/fastapi-practice/frontend-integration/notion-oauth/frontend.patch"
npm run build
npm test
```

패치가 변경하는 8개 파일의 최종 내용도 이 디렉터리의 src와 tests에 들어 있습니다.
기존 파일을 덮어쓰는 대신 패치를 사용하면 다른 프론트 작업과 충돌하는지 먼저 확인할 수 있습니다.

## 실제 연결에 필요한 서버 준비

1. Notion에서 여러 워크스페이스에 설치 가능한 OAuth Integration을 생성합니다. Read content를 허용합니다.
2. Notion 앱에 Redirect URI를 등록합니다. 로컬 기본값은 아래입니다.
   `http://localhost:5173/auth/notion/callback`
3. 백엔드 환경 변수에 NOTION_CLIENT_ID, NOTION_CLIENT_SECRET,
   NOTION_OAUTH_REDIRECT_URI, NOTION_CREDENTIAL_ENCRYPTION_KEY를 설정합니다.
   Client Secret은 채팅·Git·프론트 환경변수에 넣지 않습니다.
4. 백엔드 requirements.txt의 cryptography를 설치합니다.
5. sql/user_notion_accounts.sql을 TiDB에서 실행하고 백엔드를 재시작/배포합니다.

localhost와 127.0.0.1은 다른 사이트로 취급됩니다. 승인 시작 화면, 콜백 주소,
Notion 앱 Redirect URI의 호스트와 포트는 같아야 합니다. 배포 시에는 배포된 프론트의 HTTPS 주소를 사용합니다.
Notion 계정 연결 성공은 모든 페이지의 접근 권한을 의미하지 않습니다. 승인 화면에서 선택한 페이지 링크를 등록하세요.
첫 수집은 비교 기준을 저장합니다. 이후 수정하고 새로고침하면 수정 전·후 기록이 생깁니다.

백엔드 상세 계약과 마이그레이션은 ../../docs/notion-user-oauth.md를 참고하세요.

## 검증 결과

- 현재 프론트의 복사본에 적용 후 npm run build 성공
- 기존 테스트와 신규 승인 흐름 테스트 합계 45개 통과
- 현재 프론트 소스에 대한 git apply --check 성공
- 실제 Notion 사용자 승인, 운영 DB 변경, Render 배포는 수행하지 않음
