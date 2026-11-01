# 대시보드 / GitHub API

모든 API는 로그인 토큰과 프로젝트 소유권을 확인합니다.

| Method | 경로 | 기능 |
| --- | --- | --- |
| GET | /api/projects/{project_id}/dashboard | 미정리 개수, 최근 Story 3개, 최근 활동 5개, GitHub 정보와 커밋 5개 |
| GET | /api/projects/{project_id}/activities | 활동 목록. unorganized=true/false, source, limit, offset |
| GET | /api/projects/{project_id}/stories | Story 목록. story_status, limit, offset |
| POST | /api/projects/{project_id}/github/sync | GitHub 커밋 한 페이지를 활동으로 저장. branch, page, per_page |
| GET | /api/projects/{project_id}/github/commits | 실시간 커밋 목록. branch, page, per_page |
| GET | /api/projects/{project_id}/github/commits/{sha} | 파일 변경사항과 추가/삭제 줄 수 |
| GET | /api/projects/{project_id}/github/branches | 브랜치 목록 |

기존 /stories와 /project_activities CRUD도 유지합니다.

## 대시보드 응답

- project: 프로젝트 정보
- unorganized_counts: github, figma, notion, total. story_id가 null인 DB 활동만 집계
- recent_stories: created_at 내림차순 최근 3개 (같은 시각이면 id 내림차순)
- recent_activities: occurred_at 내림차순 최근 활동 5개 (정리 여부와 무관)
- github / recent_commits: GitHub 실시간 조회
- github_error: GitHub 조회 실패 사유. 실패해도 DB 요약은 200으로 반환

GitHub URL이 없으면 github=null, recent_commits=[]입니다.
GitHub 전용 조회와 동기화 API는 미연결 상태에서 409를 반환합니다.

## Swagger 확인 순서

1. 서버 실행 후 /docs에서 로그인하고 Authorize에 토큰 입력.
2. PATCH /projects/{id}로 github_url 설정.
3. POST /api/projects/{id}/github/sync 실행 (예: branch=main, page=1, per_page=100).
4. has_next=true이면 page를 1씩 올려 추가 동기화.
5. GET /api/projects/{id}/activities?unorganized=true 조회.
6. GET /api/projects/{id}/dashboard에서 미정리 개수 확인.
7. POST /stories로 같은 프로젝트의 Story 생성.
8. PATCH /project_activities/{activity_id}에 {"story_id": 생성한_ID} 입력.
9. 다시 대시보드 조회: 연결한 활동은 미정리 개수에서 제외.
10. {"story_id": null}로 연결 해제 가능. Story 삭제 시에도 활동은 남고 미정리로 돌아감.

동기화는 명시적으로 호출해야 합니다. GET은 DB에 저장하지 않습니다.
주기적 수집기/웹훅은 없습니다. 동일 프로젝트·저장소·SHA는 반복 수집해도 중복 저장하지 않으며
기존 Story 연결은 유지합니다. 프로젝트 행 잠금으로 동시 동기화를 직렬화합니다.
Figma/Notion 외부 수집은 별도이며, 현재 DB에 등록된 활동의 개수만 집계합니다.
비공개 저장소는 기존 GITHUB_TOKEN, GITHUB_TOKEN_OWNER_ID,
GITHUB_ALLOWED_REPOSITORIES 설정을 사용합니다. 사용자별 OAuth 토큰 저장은 구현하지 않습니다.

## 기존 DB 점검과 적용

프로젝트 루트의 .env를 그대로 사용합니다. 먼저 점검:

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_dashboard_db
```

출력된 SQL을 확인한 뒤 적용:

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_dashboard_db --apply
```

누락된 story_id, external_id, branch_name, 미정리 인덱스와 Story 외래키만 추가합니다.
이미 있는 컬럼과 데이터는 유지합니다. 기존 FK 구성이 다르면 자동 교체하지 않고 오류를 냅니다.
DDL은 일부 성공 후 실패할 수 있으므로 오류 해결 후 다시 실행합니다.
activity.updated_at은 모델과 응답에서 제외했습니다. DB에 있더라도 삭제하지 않아도 됩니다.
새 DB용 sql/schema.sql은 기본 DB명이 moeum이므로 사용 중인 DB 이름에 맞춰야 합니다.

현재 환경에서 TiDB 호스트 DNS 조회에 실패하여 원격 DB 점검과 적용은 완료되지 않았습니다.
