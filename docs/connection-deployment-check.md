# 운영 연결 설정 점검 (2026-11-25)

운영 프론트: https://moeum-log.vercel.app

## 설정과 수정

- `NOTION_OAUTH_REDIRECT_URI=https://moeum-log.vercel.app/auth/notion/callback`
- `FRONTEND_ORIGINS`에 위 origin이 포함되어야 합니다. 기존 다른 origin은 유지합니다.
- Notion 개발자 설정의 OAuth 리디렉션 목록에도 같은 콜백이 필요합니다.
- 콜백 경로와 허용 origin을 검사하고 Render에서는 HTTPS만 허용합니다.
- Notion의 401은 재연결 안내로, 403/404는 프로젝트 페이지 권한을 다시 선택하도록 안내합니다.
- 기존 사용자별 토큰 암호화와 소유자·명시적 멤버 접근 검사를 유지합니다.
- GitHub 한도 응답에서 Retry-After 또는 X-RateLimit-Reset을 읽고 인증 수단별로 외부 재호출을 차단합니다. 익명 요청은 같은 서버 IP 한도를 공유합니다. 대기는 프로세스 메모리에 보관되며 재시작 시 초기화됩니다.
- 대기 헤더를 CORS로 공개합니다. 브라우저 화면 진입 시 GitHub 자동 수집을 제거하는 프론트 변경과 함께 배포합니다.

## 확인한 범위

운영 신규 회원으로 기존 localhost 콜백 오류를 재현하고 서버·Notion 앱 설정을 수정했습니다. 수정 뒤 정상 페이지 선택 화면까지 확인했습니다. 최종 접근 승인 및 실제 Notion 토큰 교환은 미검증입니다. Figma OAuth 앱 ID가 존재하지 않는 문제는 별도로 유효한 Client ID/Secret이 필요하며 실시간 플러그인과 독립적입니다.

권한 회귀 검사 중 기존 공유 테스트가 필수 `activity_type`을 누락한 것을 수정했습니다. 공유 읽기용 시드 기록은 GitHub 기록으로 생성하며 Notion 첫 수집은 기준, 다음 편집은 변경사항 1개임을 검증합니다.

관련 백엔드 테스트 78개와 하위 검사 108개 통과. 운영 테스트 전용 프로젝트에 합성 Figma 문서를 전송해 최초 0개, 다음 편집 1개 저장과 연결 상태를 확인하고 연결을 해제했습니다. 실제 Desktop 편집 및 Notion의 최종 접근 승인은 별도 확인이 필요합니다.
