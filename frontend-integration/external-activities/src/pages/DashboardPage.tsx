import { Link, Navigate } from 'react-router';
import { services, type ServiceState } from '../data/projects';
import { useProjects } from '../state/ProjectsContext';
import { StoryCard } from '../components/StoryCard';
import { GitHubActivity } from '../components/GitHubActivity';
import { ServiceIcon, useDocumentTitle } from '../components/ui';
import ui from '../components/ui.module.css';
import styles from './DashboardPage.module.css';

export function DashboardPage() {
  useDocumentTitle('대시보드');
  const { activeProject: project, activityStates, refreshActivities } = useProjects();
  if (!project) return <Navigate to="/projects" replace />;

  return (
    <div className={styles.page}>
      <h1 className={ui.visuallyHidden}>{project.name} 대시보드</h1>
      <div className={styles.topRow}>
        <section className={`${styles.panel} ${styles.pending}`} aria-labelledby="pending-heading">
          <div className={styles.panelHeader}>
            <h2 id="pending-heading">미정리 변경사항 조회</h2>
            <Link to="/changes?period=all">변경사항 전체 보기</Link>
          </div>
          <ul className={styles.stats}>
            {services.map((service) => (
              <li key={service} className={styles.stat}>
                <span className={styles.statService}>
                  <ServiceIcon service={service} />
                  {service}
                </span>
                <PendingCount sync={activityStates[service].status} state={project.services[service]} count={project.changes.filter((change) => change.service === service).length} />
              </li>
            ))}
          </ul>
          {services.map(service => { const state = activityStates[service]; return state.status === 'error' ? <p key={service} className={styles.githubNote} role="alert">{service}: {state.error} <button type="button" className={styles.refreshButton} onClick={refreshActivities}>다시 시도</button></p> : null; })}
          <Link to="/changes?period=all" className={`${ui.primaryButton} ${styles.storyButton}`}>Story 만들기</Link>
        </section>

        <section className={styles.panel} aria-labelledby="story-heading">
          <div className={styles.panelHeader}>
            <h2 id="story-heading">최근 Story</h2>
            <Link to="/timeline">타임라인 보기</Link>
          </div>
          {project.stories.length > 0 ? (
            <ul className={styles.stories}>
              {project.stories.slice(0, 3).map((story) => <li key={story.id}><StoryCard story={story} className={styles.storyCard} /></li>)}
            </ul>
          ) : (
            <p className={styles.empty}>아직 작성된 Story가 없어요.</p>
          )}
        </section>

      </div>

      <div className={styles.bottomRow}>
        <GitHubActivity onRefresh={refreshActivities} key={project.id} url={project.urls?.GitHub ?? ''} />
      </div>
    </div>
  );
}

function PendingCount({ state, count, sync }: { state: ServiceState; count: number; sync?: string }) {
  if (sync === 'pending') return <span className={styles.muted}>조회 준비 중</span>;
  if (sync === 'loading') return <span className={styles.muted} role="status">조회 중…</span>;
  if (sync === 'error') return <span className={styles.alert}>조회 실패</span>;
  if (state.status === 'connected') {
    return <span className={styles.count}><strong>{count}</strong>개</span>;
  }
  if (state.status === 'reconnect') return <span className={styles.alert}>재연결필요</span>;
  return <span className={styles.muted}>미연결</span>;
}
