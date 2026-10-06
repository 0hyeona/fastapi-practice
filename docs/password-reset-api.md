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

`.env.example`의 `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_SSL`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM`을 `.env`에 추가하고 이메일 서비스의 SMTP
접속 정보로 채운 뒤 서버를 재시작합니다. `SMTP_PASSWORD`에는 서비스에서
요구하는 SMTP 전용 비밀번호 또는 앱 비밀번호를 사용합니다.

`SMTP_USE_SSL=false`는 STARTTLS, `true`는 연결 시작부터 SSL을 사용합니다.
SMTP 연결 구현은 [Python 공식 문서](https://docs.python.org/3/library/smtplib.html)를 따릅니다.
인증번호는 이메일로만 전달하며 API 응답이나 로그에서 조회할 수 없습니다.

## 테스트

`/docs`에서 위 표 순서대로 실행하고 실제 이메일로 받은 인증번호를 입력합니다.
자동 테스트에서는 발송 함수를 대체하여 실제 메일 없이 전체 흐름을 검사합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
