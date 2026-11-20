import { StoryLoadNotice } from '../components/StoryLoadNotice';
import { useEffect } from 'react';
import { Link, Navigate } from 'react-router';
import type { ActivityState } from '../data/activity';
import { services, type ServiceState } from '../data/projects';
import { useProjects } from '../state/ProjectsContext';
import { StoryCard } from '../components/StoryCard';
import { GitHubActivity } from '../components/GitHubActivity';
import { ServiceIcon, useDocumentTitle } from '../components/ui';
import ui from '../components/ui.module.css';
import styles from './DashboardPage.module.css';

const retryTime = new Intl.DateTimeFormat('ko-KR', {
  month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit',
});

export function DashboardPage() {
  useDocumentTitle('대시보드');
  const { activeProject: project, storyListState, activityStates, refreshActivities, figma } = useProjects();
  const { reload: reloadFigma } = figma;
  useEffect(() => reloadFigma(), [reloadFigma]);
  if (!project) return <Navigate to="/projects" replace />;

  return (
    <div className={styles.page}>
      <h1 className={ui.visuallyHidden}>{project.name} 대시보드</h1>
      <div className={styles.topRow}>
        <section className={styles.panel} aria-labelledby="pending-heading">
          <div className={`${styles.panelHeader} ${styles.pendingHeader}`}>
            <div>
              <h2 id="pending-heading">미정리 변경사항</h2>
              <p>Story로 정리할 변경사항을 서비스별로 확인해 보세요.</p>
            </div>
            <Link to="/changes?period=all">변경사항 전체 보기</Link>
          </div>
          <ul className={styles.stats}>
            {services.map(service => {
              const state = activityStates[service];
              const count = project.changes.filter(change => change.service === service).length;
              const showFigmaControls = service === 'Figma' && Boolean(project.urls?.Figma);
              const retryAt = showFigmaControls ? figma.retryAt : undefined;
              return (
                <li key={service} className={styles.stat} data-waiting={retryAt !== undefined || undefined}>
                  <span className={styles.statService}>
                    <span className={styles.statIcon}><ServiceIcon service={service} size={18} /></span>
                    {service}
                  </span>
                  <PendingCount sync={state.status} state={project.services[service]} count={count} />
                  <div className={styles.statActions}>
                    {showFigmaControls && (
                      <button type="button" className={styles.statButton} disabled={figma.refreshDisabled}
                        onClick={figma.refresh} aria-label={figma.syncing || retryAt !== undefined ? undefined : 'Figma 새로고침'}>
                        {figma.syncing ? '수집 중…' : retryAt !== undefined ? '수집 대기 중' : '새로고침'}
                      </button>
                    )}
                    {service === 'Notion' && project.urls?.Notion && (
                      <button type="button" className={styles.statButton} disabled={state.status === 'loading'}
                        onClick={() => refreshActivities(service)} aria-label={state.status === 'ready' ? 'Notion 새로고침' : undefined}>
                        {state.status === 'loading' ? '수집 중…' : state.status === 'error' ? '다시 시도' : '새로고침'}
                      </button>
                    )}
                    {state.status === 'error' && service === 'GitHub' && (
                      <button type="button" className={styles.statButton} onClick={() => refreshActivities(service)}>다시 시도</button>
                    )}
                  </div>
                  <div className={styles.statNotes}>
                    {service === 'Notion' && state.status === 'error' && (
                      <Link className={styles.statButton} to="/settings#notion-account">Notion 연결 설정</Link>
                    )}
                    {state.status === 'error' && <p className={styles.statError} role="alert">{state.error}</p>}
                    {state.status === 'error' && service === 'Figma' && (
                      <button type="button" className={styles.statButton} disabled={figma.syncing} onClick={figma.reload}>목록 다시 조회</button>
                    )}
                    {retryAt !== undefined ? (
                      <p className={styles.retryNote} role="status" title={figma.notice}>
                        <time dateTime={new Date(retryAt).toISOString()}>{retryTime.format(retryAt)}</time> 이후 다시 시도
                      </p>
                    ) : showFigmaControls && figma.notice && (
                      <p className={figma.error ? styles.statError : undefined} role={figma.error ? 'alert' : 'status'}>{figma.notice}</p>
                    )}
                    {showFigmaControls && figma.hasMore && <p>이어 수집할 기록이 있어요.</p>}
                  </div>
                </li>
              );
            })}
          </ul>
          <div className={styles.pendingFooter}>
            <Link to="/changes?period=all" className={`${ui.primaryButton} ${styles.storyButton}`}>
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M8 3v10M3 8h10" /></svg>
              Story 만들기
            </Link>
          </div>
        </section>

        <section className={styles.panel} aria-labelledby="story-heading">
          <div className={styles.panelHeader}>
            <h2 id="story-heading">최근 Story</h2>
            <Link to="/timeline">타임라인 보기</Link>
          </div>
          <StoryLoadNotice />
          {project.stories.length > 0 ? (
            <ul className={styles.stories}>
              {project.stories.slice(0, 3).map((story) => <li key={story.id}><StoryCard story={story} className={styles.storyCard} /></li>)}
            </ul>
          ) : storyListState.status === 'ready' ? (
            <p className={styles.empty}>아직 작성된 Story가 없어요.</p>
          ) : null}
        </section>

      </div>

      <div className={styles.bottomRow}>
        <GitHubActivity onRefresh={() => refreshActivities('GitHub')} key={project.id} url={project.urls?.GitHub ?? ''} />
      </div>
    </div>
  );
}

function PendingCount({ state, count, sync }: { state: ServiceState; count: number; sync: ActivityState['status'] }) {
  if (sync === 'pending') return <span className={styles.statStatus}>조회 준비 중</span>;
  if (sync === 'loading') return <span className={styles.statStatus} role="status">조회 중…</span>;
  if (sync === 'error') return <span className={`${styles.statStatus} ${styles.statError}`}>조회 실패</span>;
  if (state.status === 'connected') {
    return <span className={styles.count}><strong>{count}</strong>개</span>;
  }
  if (state.status === 'reconnect') return <span className={`${styles.statStatus} ${styles.statError}`}>재연결 필요</span>;
  return <span className={styles.statStatus}>미연결</span>;
}
