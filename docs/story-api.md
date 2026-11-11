# S5 · S7 · S9 Story API

로그인 응답의 액세스 토큰을 `Authorization: Bearer <token>` 헤더로 전달합니다.
`/stories` 경로에는 `/api` 접두사가 없습니다.

| 작업 | API |
| --- | --- |
| 미정리 변경사항 조회 | `GET /api/projects/{project_id}/activities?unorganized=true` |
| 선택한 변경사항 AI 분석 | `POST /stories/analyze` |
| 생성 | `POST /stories` |
| 상세 조회 | `GET /stories/{story_id}` |
| 프로젝트별 목록 | `GET /stories?project_id={project_id}` |
| 부분 수정 | `PATCH /stories/{story_id}` |
| 삭제 | `DELETE /stories/{story_id}` |
| Markdown 내보내기 | `GET /stories/{story_id}/export` |
| Story에 연결된 변경사항 조회 | `GET /api/projects/{project_id}/activities?story_id={story_id}` |
| 변경사항 단건 연결·해제 | `PATCH /project_activities/{activity_id}` |

## S5 변경사항 분석

활동 목록의 `activity_id`를 사용합니다. `source=github`, `source=figma`, `source=notion`으로
목록을 필터링할 수 있습니다. 분석은 같은 프로젝트의 활동 1~20개를 받습니다.

```json
{"project_id": 1, "activity_ids": [12, 18, 23]}
```

`POST /stories/analyze`의 응답은 아래와 같습니다.

```json
{
  "tags": ["로그인", "인증"],
  "title": "로그인 화면 개선",
  "before": null,
  "after": "인증 만료 시 로그인 화면으로 이동",
  "summary": "로그인 화면을 정리하고 인증 만료 시 안내를 추가했습니다."
}
```

근거가 부족한 `before` 또는 `after`는 `null`입니다. `section`에 `tags`, `title`, `before`, `after`,
`summary` 중 하나를 전달하면 해당 필드만 반환하므로 화면에서 그 값만 교체할 수 있습니다.
이 호출은 Story를 저장하거나 활동을 연결하지 않습니다.

서버의 `OPENAI_API_KEY`를 설정하면 AI 분석을 사용할 수 있습니다. `OPENAI_STORY_MODEL` 기본값은
`gpt-4.1-mini`입니다. 요청하면 선택한 활동의 출처, 유형, 제목, 설명(활동당 최대 3,000자),
발생 시간을 OpenAI에 전송합니다. 키가 없으면 503, 분석 응답에 문제가 있으면 502, 시간 초과는 504입니다.

## S7 생성 및 활동 연결

`project_id`는 로그인한 사용자가 소유한 실제 프로젝트 ID로 바꿉니다.

```json
{
  "project_id": 1,
  "title": "Story 저장 기능 구현",
  "content": "회고에 참고할 메모",
  "story_status": "draft",
  "why": "작성 내용을 다시 조회하기 위해",
  "problem": "세부 내용이 저장되지 않음",
  "solution": "모델과 요청·응답 스키마에 필드 추가",
  "result": "작성 내용 저장 및 재조회",
  "learned": "DB와 API 필드 매핑",
  "next_steps": "프론트 화면 연결",
  "activity_ids": [12, 18, 23],
  "ai_analysis": {
    "tags": ["API", "저장"],
    "summary": "작성한 내용을 저장하고 다시 조회할 수 있습니다.",
    "before": "세부 내용이 저장되지 않음",
    "after": "세부 내용을 저장하고 조회함"
  }
}
```

생성 응답은 201이며, `id`로 상세 조회하면 저장한 Story가 반환됩니다.
`story_status`는 `draft` 또는 `published`이며 DB의 기존 `status` 컬럼에 저장됩니다.
S7·S9의 메모는 기존 `content`에, 태그는 `ai_analysis.tags`에 매핑합니다.
S5 응답의 `title`은 편집한 뒤 Story의 최상위 `title`로 전달합니다.

본문 필드 6개는 각각 최대 15,000자의 문자열 또는 null입니다.
`ai_analysis`는 JSON 값(객체, 배열, 문자열 등) 또는 null을 받습니다.
기존과 같이 본문·분석을 생략한 생성 요청도 지원합니다.

`activity_ids`는 선택 사항입니다. 보내면 Story와 연결이 함께 저장됩니다. 존재하지 않거나 다른
프로젝트에 속한 ID는 404, 이미 연결된 활동이 있으면 409이며 Story와 연결 모두 저장되지 않습니다.
기존 Story에는 단건 연결 API로 `{"story_id": 3}`을 보내고, 해제할 때는 `{"story_id": null}`을 보냅니다.

## S9 조회, 수정 및 내보내기

PATCH에서 생략한 필드는 유지됩니다. 본문 6개와 `ai_analysis`는 null로 초기화할 수 있습니다.
`title`, `content`, `story_status`는 null로 바꿀 수 없습니다.
`ai_analysis`를 수정할 때는 기존 JSON을 화면에서 병합한 다음 전달합니다. PATCH는 해당 필드 전체를 교체합니다.
메모를 지우려면 `content`를 빈 문자열로, 태그를 지우려면 `ai_analysis.tags`를 빈 배열로 전달합니다.

`GET /stories/{story_id}/export`는 저장된 Story를 UTF-8 Markdown으로 반환합니다.
`Content-Disposition`의 파일명은 `story-{story_id}.md`입니다.
