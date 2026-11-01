# Activity updated_at 호환성

현재 활동 모델과 응답에서는 updated_at을 사용하지 않습니다.
DB에 updated_at이 없어도 정상 동작하며, 이미 있으면 그대로 유지해도 됩니다.
과거의 sql/migrate_project_activities_updated_at.sql은 현재 코드에 필수인 마이그레이션이 아닙니다.

대시보드에 필요한 story_id, external_id, branch_name 및 외래키 점검은
프로젝트 루트에서 python -m scripts.setup_dashboard_db 로 실행합니다.
자세한 사용 순서는 github-dashboard-api.md를 참고하세요.
