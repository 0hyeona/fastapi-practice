# Figma manual collection

Page entry: GET /project_activities?project_id={id}&source=figma.
This reads stored activities only. Do not POST sync on mount or navigation.

Refresh: GET /api/projects/{id}/figma/sync-status, then POST
/api/projects/{id}/figma/sync only when can_sync is true. The POST also
enforces the gate atomically, so the status check cannot bypass it.
After success reload the stored activities. On failure keep the displayed
activities and show the error separately. Frontend wiring is still required.

Status: running, can_sync, retry_after_seconds, next_sync_at, last_success_at.
Times in the status API have UTC offsets. Figma upstream 429 is returned as
429 with Retry-After. The deadline is persisted as JSON in the existing
project_sync_runs.error_message field (error_code=429); no migration required.
When the header is absent/invalid, a one-hour fallback is used. It is not a
claim that the upstream quota resets in one hour.

FIGMA_SYNC_MIN_INTERVAL_SECONDS defaults to 600. Applies to pagination too.
This does not reset monthly quotas. A new token does not reset user quotas.
Link saves no longer queue Figma collection; Notion behavior is unchanged.

Admission locks the projects row before checking history and inserting a
running run. Network work starts only after that transaction commits.
This coordinates workers using the same TiDB. SQLite unit tests do not prove
TiDB concurrency; verify with two concurrent requests in staging.

A process crash can leave a running row. It deliberately remains blocked:
after verifying no collector is alive, an operator must mark that specific
run failed with a finished_at time. Never clear a live collector's run.
Rate gating is per project; a shared Figma token can also hit a quota shared
across projects. Such requests still record and respect their upstream 429.
