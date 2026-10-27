# 비밀번호 찾기 API 연결

모든 요청은 JSON이며 주소 앞에 `/api/auth/password`를 붙입니다.
로그인 토큰은 필요하지 않습니다. 회원가입 API에서 이메일 중복 `409`가 발생하면
프론트엔드가 비밀번호 찾기 페이지로 이동하고 입력한 이메일을 전달합니다.

| 화면 동작 | POST 경로 | 요청 | 성공 응답 |
| --- | --- | --- | --- |
| 다음: 이메일 확인 | `/check-email` | `email` | `200`, `message` |
| 인증번호 받기 / 재발송 | `/request-code` | `email` | `200`, `message` |
| 인증번호 확인 | `/verify-code` | `email`, `code` | `200`, `reset_token`, `expires_in: 600` |
| 비밀번호 변경 완료 | `/reset` | `reset_token`, `new_password`, `confirm_password` | `200`, `message` |

이메일 확인 요청:

```json
{"email": "testuser@example.com"}
```

인증번호 발송도 위와 같은 요청을 사용합니다. 이메일로 받은 인증번호는
숫자가 아닌 문자열로 보내야 앞자리 `0`이 유지됩니다.

```json
{"email": "testuser@example.com", "code": "012345"}
```

인증 성공 응답의 `reset_token`을 다음 화면으로 전달합니다. 로그인용
`access_token`과 다른 값이며 비밀번호 재설정에 한 번만 사용할 수 있습니다.

```json
{
  "reset_token": "인증 성공 응답에서 받은 값",
  "new_password": "New-pass123!",
  "confirm_password": "New-pass123!"
}
```

새 비밀번호는 그림에 맞춰 영문·숫자·특수문자를 각각 포함한 8~16자이며
공백은 허용하지 않습니다. 재입력 값이 일치해야 합니다. 프론트엔드에서도
같은 규칙으로 버튼 활성화와 오류 문구를 표시하고 서버가 최종 검증합니다.

| 응답 코드 | 화면 처리 |
| --- | --- |
| `404` | 등록되지 않은 이메일 안내 |
| `400` | 인증번호 오류·만료 또는 재설정 토큰 오류·만료 안내 |
| `422` | 이메일 형식, 6자리 인증번호, 비밀번호 규칙·불일치 안내 |
| `429` | 인증번호 재발송까지 60초 대기 |
| `503` | 이메일 발송 설정 누락 또는 발송 실패 안내 |

일반 오류 메시지는 `detail` 문자열입니다. `422`는 FastAPI 검증 오류 배열이므로
`detail` 배열의 `loc`와 `msg`를 사용해 필드 오류를 표시합니다.

인증번호와 재설정 토큰은 각각 10분 유효합니다. 인증번호를 5번 틀리면
재발송해야 합니다. 재발송하면 이전 인증번호와 재설정 토큰은 무효입니다.
변경 완료 시 기존 로그인 세션이 모두 삭제되므로 로그인 페이지로 이동합니다.
이메일 존재 여부는 요청한 화면 흐름에 맞춰 응답하며 비활성 회원은 제외합니다.

## DB 준비

`sql/schema.sql`에 `password_resets` 테이블이 포함되어 있습니다. 기존 DB에는
아래 명령으로 해당 테이블만 추가할 수 있습니다. 기존 회원은 유지됩니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_password_db
```

회원별로 최신 요청 1개를 저장합니다. 인증번호는 Argon2 해시, 재설정 토큰은
SHA-256 해시로 저장하며 원문은 DB에 저장하지 않습니다. 날짜는 UTC입니다.

## 실제 이메일 발송 설정

본인의 Gmail 계정으로 다른 사람에게 인증번호를 보냅니다. 도메인 구매나 SMTP 설정은 필요하지 않습니다.
Google OAuth로 **발신자 한 명**이 Gmail 발송 권한을 허용합니다. 인증번호를 받는 회원은 Google 로그인이나 테스트 사용자 등록이 필요하지 않습니다.
이 기능은 서비스 회원의 Google 로그인과 별개입니다. 기존 `SMTP_*`, `RESEND_*` 환경변수는 사용하지 않습니다.
기존 httpx로 Gmail HTTPS API를 호출하므로 추가 패키지는 필요하지 않습니다.

### 1. Google Cloud 준비

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성하거나 선택합니다.
2. APIs & Services → Library에서 **Gmail API**를 검색해 사용 설정(Enable)합니다.
3. Google Auth Platform에서 앱 이름, 지원 이메일, 연락처를 설정합니다. 개인 Gmail은 Audience를 External로 설정합니다.
4. Data Access에서 `https://www.googleapis.com/auth/gmail.send` 범위만 추가합니다.
5. Testing 상태에서는 Audience의 Test users에 **발신에 사용할 본인 Gmail**을 추가합니다.
6. Clients → Create client에서 **Web application**을 선택합니다. Authorized redirect URIs에 아래 주소를 정확히 등록하고 저장합니다.

```text
https://developers.google.com/oauthplayground
```

7. 생성된 Client ID와 Client secret을 보관합니다. API 키나 서비스 계정 키가 아닌 OAuth 클라이언트 정보입니다.

### 2. 발신 Gmail 권한 허용 및 refresh token 발급

1. [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)를 엽니다.
2. 오른쪽 위 설정(톱니바퀴)에서 **Use your own OAuth credentials**를 켜고 위에서 만든 Client ID와 Client secret을 입력합니다.
3. Access type은 **Offline**, 동의 화면은 **Consent**로 설정합니다.
4. Step 1에 `https://www.googleapis.com/auth/gmail.send`를 입력하고 Authorize APIs를 누릅니다.
5. **발신자로 사용할 본인의 Gmail 계정**으로 로그인하고 발송 권한을 허용합니다.
6. Step 2의 **Exchange authorization code for tokens**를 누릅니다.
7. 표시된 **Refresh token**을 보관합니다. Access token은 짧게 만료되므로 Render에 대신 넣으면 안 됩니다.

Playground 기본 자격증명이 아닌 **본인의 OAuth 자격증명**으로 발급해야 합니다.
Testing 상태에서 Gmail 범위로 발급한 refresh token은 일반적으로 **7일 후 만료**됩니다.
지속 운영하려면 Audience의 Publishing status를 In production으로 바꾼 뒤 권한을 다시 허용하고 새 refresh token을 등록하세요.
Production 전환과 Google 검증 완료는 별개이며, 사용 방식과 Google 정책에 따라 검증이 필요할 수 있습니다.
발신 계정의 권한 취소, 비밀번호 변경 등으로 토큰이 무효가 되면 다시 발급해야 합니다.

### 3. Render 환경변수

백엔드 서비스 → Environment에 아래 네 값을 저장한 뒤 변경된 코드를 배포합니다.

| 환경변수 | 입력할 값 |
| --- | --- |
| `GMAIL_CLIENT_ID` | Google OAuth Client ID |
| `GMAIL_CLIENT_SECRET` | 같은 OAuth 클라이언트의 Client secret |
| `GMAIL_REFRESH_TOKEN` | 위에서 발신 계정으로 발급한 Refresh token |
| `GMAIL_FROM_EMAIL` | 권한을 허용한 본인의 Gmail 주소, 예: `myaccount@gmail.com` |

발신 주소는 권한을 허용한 Gmail 계정과 일치시킵니다.
Client secret과 refresh token은 Render 백엔드 환경변수에만 저장하고 Git이나 프론트엔드에 넣지 않습니다.
로컬 실행은 루트 `.env`에 동일한 네 값을 넣고 서버를 재시작합니다. Render에 `.env`를 업로드할 필요는 없습니다.
기존 프론트엔드의 `/check-email` → `/request-code` → `/verify-code` → `/reset` 순서는 그대로 사용합니다.
수신 이메일이 우리 서비스에 가입되어 있으면 본인의 Gmail에서 해당 주소로 인증번호를 발송합니다.

### 발송 실패 확인

설정 누락 또는 Google API 실패는 `503`으로 응답하고 인증번호 저장을 롤백합니다.
Render에 네 변수가 모두 들어 있는지, Gmail API가 활성화되었는지, refresh token이 동일한 Client ID로 발급되었는지 확인하세요.
Google의 `invalid_grant`는 토큰 만료/취소 등을 의미하므로 발신 계정으로 권한을 다시 허용하고 refresh token을 교체합니다.
Gmail의 일일 발송 한도와 스팸 방지 정책도 적용되며 무제한 발송 서비스가 아닙니다.
인증번호, OAuth 토큰 및 Google의 원본 오류 응답은 API 응답이나 로그에 출력하지 않습니다.

참고: [Gmail 발송 형식](https://developers.google.com/workspace/gmail/api/guides/sending),
[OAuth 토큰 갱신](https://developers.google.com/identity/protocols/oauth2/web-server#offline),
[Refresh token 만료 조건](https://developers.google.com/identity/protocols/oauth2#expiration).

## 테스트

`/docs`에서 위 표 순서대로 실행하고 실제 이메일로 받은 인증번호를 입력합니다.
자동 테스트에서는 발송 함수를 대체하여 실제 메일 없이 전체 흐름을 검사합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
