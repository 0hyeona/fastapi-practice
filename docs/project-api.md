# 프로젝트 API

기존 MySQL `projects` 테이블에 연결합니다. 서버는 이미 저장한 프로젝트를 지우거나
예시 데이터를 자동으로 추가하지 않습니다. 새 DB는 `sql/schema.sql`로 준비합니다.

## Swagger 사용

1. `/docs`에서 `POST /api/auth/login`으로 로그인합니다.
2. 응답의 `access_token`을 복사합니다.
3. 페이지 위쪽 **Authorize**에서 HTTPBearer의 Value에 토큰만 입력하고 인증합니다.
4. `projects` 항목에서 **Try it out**으로 아래 API를 실행합니다.

| API | 역할 | 성공 응답 |
| --- | --- | --- |
| `POST /projects` | 프로젝트 생성 | `201`과 생성한 프로젝트 |
| `GET /projects` | 로그인한 회원의 프로젝트 목록 | `200`과 배열 |
| `GET /projects/{project_id}` | 로그인한 회원의 프로젝트 상세 | `200`과 프로젝트 |
| `PATCH /projects/{project_id}` | 본인 프로젝트 부분 수정 | `200`과 수정된 프로젝트 |
| `DELETE /projects/{project_id}` | 본인 프로젝트 영구 삭제 | `204`, 응답 본문 없음 |
| `PATCH /projects/{project_id}/archive` | 본인 프로젝트 보관 | `200`과 보관된 프로젝트 |
| `PATCH /projects/{project_id}/restore` | 본인 프로젝트 보관 해제 | `200`과 활성 프로젝트 |

생성 요청:

```json
{
  "project_name": "MOEUM",
  "description": "프로젝트 변경사항을 기록하고 관리하는 서비스",
  "github_url": "https://github.com/0hyeona/fastapi-practice",
  "figma_url": null,
  "notion_url": null
}
```

세 URL은 선택 항목입니다. 생략, `null`, 빈 문자열은 DB에 `NULL`로 저장됩니다.
입력한 링크는 최대 2,048자의 HTTP/HTTPS URL이어야 하며, 잘못된 형식은 `422`를 반환합니다.
생성·목록·상세 응답은 모두 `github_url`, `figma_url`, `notion_url`을 포함합니다.
프론트는 값이 있는 서비스의 아이콘을 표시하고, 클릭하면 해당 URL을 열면 됩니다.
링크 등록은 서비스 계정 인증이나 외부 데이터 조회를 수행하지 않습니다.

기존 DB에서 세 컬럼을 아직 추가하지 않았다면 `sql/migrate_project_urls.sql`을 한 번
실행한 뒤 서버를 실행합니다. 이미 컬럼을 추가한 DB에는 다시 실행하지 마세요.
Render 등 배포 환경의 DB에도 컬럼이 있어야 합니다. 새 DB는 갱신된 `sql/schema.sql`을 사용합니다.

`owner_id`는 로그인한 회원의 `users.id`를 사용합니다. 요청에 직접 넣을 경우에도
로그인한 회원 번호와 같아야 하며, 다른 회원 번호를 넣으면 `403`을 반환합니다.
프로젝트 이름은 앞뒤 공백을 제거한 1~100자, 설명은 생략 가능하며 최대 10,000자입니다.

목록은 기본적으로 `active` 프로젝트만 최신 프로젝트부터 반환합니다. `limit`은 기본 50, 최대 100이고 `offset`으로
다음 목록을 조회합니다. 다른 회원의 프로젝트는 목록에 포함하지 않습니다.
상세 조회에서 프로젝트가 없거나 다른 회원 소유라면 `404`를 반환합니다.
인증되지 않은 요청은 `401`, 입력 형식 오류는 `422`를 반환합니다.

Workbench에서 `owner_id=4`로 저장한 기존 프로젝트는 **회원 번호 4로 로그인한 뒤**
`GET /projects`에서 확인할 수 있습니다. 같은 이름의 프로젝트를 다시 생성하면
새로운 행이 추가됩니다.

## 보관 및 보관 해제

보관은 기존 `project_status`를 `archived`로 바꿉니다. 이름, 설명, 연결 URL과 DB 행은
유지되며 상태가 바뀔 때 `updated_at`도 갱신됩니다. 별도 DB 컬럼 추가는 필요 없습니다.

Swagger에서 프로젝트 번호를 입력하고 아래 순서로 실행합니다. 요청 본문은 없습니다.

1. `PATCH /projects/{project_id}/archive`: 응답의 `project_status`가 `archived`인지 확인
2. `GET /projects`: 기본 목록에서 해당 프로젝트가 빠지는지 확인
3. `GET /projects?project_status=archived`: 보관 목록에서 해당 프로젝트 확인
4. `PATCH /projects/{project_id}/restore`: 응답의 상태가 `active`이고 기본 목록에 다시 표시되는지 확인

`project_status=all`이면 활성 및 보관 프로젝트를 함께 조회합니다. 상태 필터를 적용한 뒤
페이지를 나눕니다. 상세 조회는 보관된 프로젝트도 조회할 수 있습니다.
이미 보관된 프로젝트를 다시 보관하거나 활성 프로젝트를 다시 복원하면 현재 정보를
`200`으로 반환하며 추가 변경은 하지 않습니다. 다른 회원 소유 또는 없는 프로젝트는
`404`, 로그인하지 않은 요청은 `401`을 반환합니다.

## 수정 및 삭제

수정 요청에는 바꿀 필드만 넣습니다. 생략한 필드는 그대로 유지합니다.
이름, 설명, GitHub/Figma/Notion URL을 수정할 수 있으며 보관된 프로젝트도 수정할 수 있습니다.
회원 번호, 상태, 프로젝트 번호와 날짜는 수정 요청으로 변경할 수 없습니다.

```json
{
  "project_name": "MOEUM 수정",
  "description": "새 설명",
  "figma_url": null
}
```

설명과 URL은 `null`로 비울 수 있습니다. URL은 빈 문자열도 `null`로 처리합니다.
이름은 `null` 또는 공백으로 바꿀 수 없습니다. 빈 요청 `{}`, 잘못된 URL, 허용하지 않은
필드가 있으면 `422`를 반환합니다. 변경된 내용이 있으면 `updated_at`을 갱신합니다.

삭제는 DB 행을 제거하는 영구 삭제이며 되돌릴 수 없습니다. 테스트용 프로젝트에서
`DELETE /projects/{project_id}`를 실행하고 `204`를 확인합니다. 삭제한 프로젝트를
상세 조회하면 `404`이고 목록에서도 제외됩니다. 다시 삭제해도 `404`입니다.
수정과 삭제 모두 다른 회원 소유 또는 없는 프로젝트는 `404`, 미로그인은 `401`입니다.
