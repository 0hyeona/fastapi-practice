# S7 Story API

로그인 응답의 액세스 토큰을 `Authorization: Bearer <token>` 헤더로 전달합니다.
현재 라우터 경로에는 `/api` 접두사가 없습니다.

| 작업 | API |
| --- | --- |
| 생성 | `POST /stories` |
| 상세 조회 | `GET /stories/{story_id}` |
| 프로젝트별 목록 | `GET /stories?project_id={project_id}` |
| 부분 수정 | `PATCH /stories/{story_id}` |
| 삭제 | `DELETE /stories/{story_id}` |

## 생성 예시

`project_id`는 로그인한 사용자가 소유한 실제 프로젝트 ID로 바꿉니다.

```json
{
  "project_id": 1,
  "title": "Story 저장 기능 구현",
  "content": "작업 내용 요약",
  "story_status": "draft",
  "why": "작성 내용을 다시 조회하기 위해",
  "problem": "세부 내용이 저장되지 않음",
  "solution": "모델과 요청·응답 스키마에 필드 추가",
  "result": "작성 내용 저장 및 재조회",
  "learned": "DB와 API 필드 매핑",
  "next_steps": "프론트 화면 연결",
  "ai_analysis": {
    "summary": "분석 결과",
    "suggestions": ["조회 결과 확인"]
  }
}
```

생성 응답은 201이며, `id`로 상세 조회하면 같은 필드가 반환됩니다.
`story_status`는 `draft` 또는 `published`이며 DB의 기존 `status` 컬럼에 저장됩니다.

새 본문 필드 6개는 각각 최대 15,000자의 문자열 또는 null입니다.
`ai_analysis`는 JSON 값(객체, 배열, 문자열 등) 또는 null을 받습니다.
분석 결과를 저장하는 기능이며 AI 분석 자체를 실행하지는 않습니다.
새 필드를 생략한 기존 생성 요청도 지원하며, 새 필드 기본값은 null입니다.

PATCH에서 생략한 필드는 유지됩니다. 새 필드는 null로 초기화할 수 있습니다.
`title`, `content`, `story_status`는 null로 바꿀 수 없습니다.

## DB 확인 및 검증 범위

이 변경은 DB 스키마를 수정하지 않습니다. 모델은 새 본문 6개를 nullable TEXT,
`ai_analysis`를 nullable JSON으로 매핑합니다. 운영 DB의 컬럼 타입은 별도로 확인해야 합니다.

```sql
USE moeum_db;
SHOW COLUMNS FROM stories;
```

로컬 SQLite의 서비스 테스트로 새 필드 저장·재조회·응답 변환·부분 수정·null 초기화를 검증합니다.
HTTP 회귀 테스트도 추가했으나 이 작업 환경의 Windows 이벤트 루프 초기화가 멈춰 완료하지 못했습니다.
TiDB 연결은 작업 환경의 DNS 오류로 확인하지 못했습니다.
배포 후 Swagger에서 위 예시로 POST → GET을 실행하면 실제 TiDB 저장 경로를 확인할 수 있습니다.
