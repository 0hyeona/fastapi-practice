import { useRef, useState, type KeyboardEvent } from 'react';
import { Navigate, useNavigate } from 'react-router';
import errorIcon from '../../assets/icons/error.svg';
import type { Project, Service } from '../data/projects';
import { githubRepository } from '../data/github';
import { useProjects } from '../state/ProjectsContext';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { NotionConnection } from '../components/NotionConnection';
import { ServiceIcon, useDocumentTitle } from '../components/ui';
import form from '../components/form.module.css';
import ui from '../components/ui.module.css';
import styles from './SettingsPage.module.css';

// 디자인의 연동 서비스 순서입니다.
const settingServices: readonly Service[] = ['GitHub', 'Notion', 'Figma'];

export function SettingsPage() {
  useDocumentTitle('프로젝트 설정');
  const { activeProject: project, deleteProject } = useProjects();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  if (!project) return <Navigate to="/projects" replace />;

  async function confirmDelete() {
    if (deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteProject();
      navigate('/projects', { replace: true });
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '프로젝트를 삭제하지 못했습니다.');
    } finally { setDeleting(false); }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}><h1>프로젝트 설정</h1><p>프로젝트의 기본 정보와 연결된 서비스를 관리해요.</p></header>
      <div className={styles.sections}>
        {/* 헤더에서 프로젝트를 바꾸면 입력 중이던 값을 새 프로젝트 값으로 다시 채웁니다. */}
        <ProjectInfo key={project.id} project={project} />
        <Connections key={`connections-${project.id}`} project={project} />

        <section className={`${styles.panel} ${styles.dangerPanel}`} aria-labelledby="danger-heading">
          <SectionHeader id="danger-heading" title="프로젝트 삭제" description="프로젝트를 더 이상 사용하지 않을 때 삭제할 수 있어요." />
          <div className={styles.danger}>
            <div className={styles.alert}>
              <p className={styles.alertTitle}>
                <img src={errorIcon} alt="" width={24} height={24} />
                삭제하면 복구할 수 없어요
              </p>
              <p className={styles.alertText}>프로젝트와 모든 Story가 영구적으로 삭제돼요. 필요한 기록을 먼저 확인해주세요.</p>
            </div>
            <button type="button" className={`${ui.dangerButton} ${styles.deleteButton}`} onClick={() => setConfirming(true)}>프로젝트 삭제</button>
          </div>
        </section>
      </div>

      {confirming && (
        <ConfirmDialog
          title="프로젝트를 삭제할까요?"
          description={`‘${project.name}’ 프로젝트와 모든 Story가 삭제되고 되돌릴 수 없어요.`}
          confirmLabel={deleting ? '삭제 중…' : '삭제'}
          pending={deleting}
          onConfirm={confirmDelete}
          onCancel={() => setConfirming(false)}
        >
          {deleteError && <p className={form.error} role="alert">{deleteError}</p>}
        </ConfirmDialog>
      )}
    </div>
  );
}

type Announcement = { id: number; text: string };

function useAnnouncement() {
  const [message, setMessage] = useState<Announcement | null>(null);
  const announce = (text: string) => setMessage((current) => ({ id: (current?.id ?? 0) + 1, text }));
  return [message, announce, () => setMessage(null)] as const;
}

// 같은 문구가 다시 나와도 읽히도록, 라이브 영역은 그대로 두고 안쪽 텍스트 노드만 새로 그립니다.
function StatusText({ message }: { message: Announcement | null }) {
  return (
    <span className={styles.status} role="status">
      {message && <span key={message.id}>{message.text}</span>}
    </span>
  );
}

function SectionHeader({ id, title, description }: { id: string; title: string; description: string }) {
  return (
    <div className={styles.sectionHeader}>
      <h2 id={id}>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

type InfoField = 'name' | 'description';

function ProjectInfo({ project }: { project: Project }) {
  const { updateProject } = useProjects();
  const [draft, setDraft] = useState({ name: project.name, description: project.description });
  const [nameError, setNameError] = useState('');
  const [savedField, setSavedField] = useState<InfoField | null>(null);
  const [saved, announceSaved, clearSaved] = useAnnouncement();
  const saving = useRef(false);
  const [pending, setPending] = useState(false);
  const [saveError, setSaveError] = useState('');

  function change(field: InfoField, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
    clearSaved();
    if (field === 'name') setNameError('');
  }

  // blur나 Enter에서 바뀐 값만 저장합니다. 프로젝트명이 비어 있으면 저장하지 않고 오류를 보여줍니다.
  async function commit(field: InfoField) {
    if (saving.current) return;
    const value = draft[field].trim();
    if (field === 'name' && !value) {
      setNameError('프로젝트명을 입력해주세요.');
      return;
    }
    setDraft((current) => ({ ...current, [field]: value }));
    if (value === project[field]) return;
    setSavedField(field);
    saving.current = true;
    setPending(true);
    setSaveError('');
    announceSaved('저장 중…');
    try {
      await updateProject({ [field]: value });
      announceSaved('저장했어요.');
    } catch (error) {
      clearSaved();
      setSaveError(error instanceof Error ? error.message : '저장하지 못했습니다. 다시 시도해주세요.');
    } finally { saving.current = false; setPending(false); }
  }

  function commitOnEnter(event: KeyboardEvent<HTMLInputElement>, field: InfoField) {
    if (event.key !== 'Enter' || event.nativeEvent.isComposing) return;
    event.preventDefault();
    commit(field);
  }

  return (
    <section className={styles.panel} aria-labelledby="info-heading">
      <SectionHeader id="info-heading" title="프로젝트 정보" description="수정 후 Enter를 누르거나 입력칸을 벗어나면 자동으로 저장돼요." />
      {saveError && <p className={form.error} role="alert">{saveError}</p>}
      <fieldset className={`${styles.fields} ${styles.fieldset}`} disabled={pending} aria-busy={pending}>
        <div className={form.field}>
          <div className={form.labelRow}>
            <label htmlFor="settings-name" className={form.label}>프로젝트명 (필수)</label>
            <StatusText message={savedField === 'name' ? saved : null} />
          </div>
          <input
            id="settings-name"
            className={`${form.input} ${styles.input}`}
            placeholder="flowlog"
            maxLength={50}
            autoComplete="off"
            value={draft.name}
            onChange={(event) => change('name', event.target.value)}
            onBlur={() => commit('name')}
            onKeyDown={(event) => commitOnEnter(event, 'name')}
            aria-invalid={!!nameError}
            aria-describedby={nameError ? 'settings-name-error' : undefined}
            required
          />
          {nameError && <p className={form.error} id="settings-name-error" role="alert">{nameError}</p>}
        </div>
        <div className={form.field}>
          <div className={form.labelRow}>
            <label htmlFor="settings-description" className={form.label}>프로젝트 설명</label>
            <StatusText message={savedField === 'description' ? saved : null} />
          </div>
          <input
            id="settings-description"
            className={`${form.input} ${styles.input}`}
            placeholder="AI Project Journal"
            maxLength={120}
            autoComplete="off"
            value={draft.description}
            onChange={(event) => change('description', event.target.value)}
            onBlur={() => commit('description')}
            onKeyDown={(event) => commitOnEnter(event, 'description')}
          />
        </div>
      </fieldset>
    </section>
  );
}

const urlFields = { GitHub: 'github_url', Figma: 'figma_url', Notion: 'notion_url' } as const;

function Connections({ project }: { project: Project }) {
  const { updateProject } = useProjects();
  const [draft, setDraft] = useState(project.urls ?? { GitHub: '', Figma: '', Notion: '' });
  const [pending, setPending] = useState<Service | null>(null);
  const busy = useRef(false);
  const [error, setError] = useState('');
  const [message, announce] = useAnnouncement();

  async function save(service: Service, disconnect = false) {
    if (busy.current) return;
    const value = disconnect ? '' : draft[service].trim();
    if (!disconnect && service === 'GitHub' && !githubRepository(value)) {
      setError('https://github.com/소유자/저장소 형식의 URL을 입력해주세요.');
      return;
    }
    if (!disconnect) {
      try {
        const url = new URL(value);
        const hosts = { GitHub: /(^|\.)github\.com$/, Figma: /(^|\.)figma\.com$/, Notion: /(^|\.)(notion\.so|notion\.site|notion\.com)$/ };
        if (url.protocol !== 'https:' || !hosts[service].test(url.hostname)) throw new Error();
      } catch { setError(service + '의 올바른 https URL을 입력해주세요.'); return; }
    }
    busy.current = true;
    setPending(service);
    setError('');
    try {
      await updateProject({ [urlFields[service]]: value || null });
      setDraft(current => ({ ...current, [service]: value }));
      announce(service + (disconnect ? ' URL을 해제했어요.' : ' URL을 저장했어요.'));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '저장하지 못했습니다.');
    } finally { busy.current = false; setPending(null); }
  }

  return <section className={styles.panel} aria-labelledby="tools-heading">
    <SectionHeader id="tools-heading" title="연동 서비스" description="프로젝트에서 사용할 작업 도구의 URL을 관리합니다." />
    <NotionConnection />
    <StatusText message={message} />
    {error && <p className={form.error} role="alert">{error}</p>}
    <fieldset className={styles.fieldset} disabled={pending !== null} aria-busy={pending !== null}>
      <ul className={styles.services}>
        {settingServices.map(service => <li key={service} className={styles.service}>
          <div className={styles.serviceInfo}>
            <div className={styles.serviceHeading}><label htmlFor={'settings-url-' + service} className={styles.serviceName}><ServiceIcon service={service} />{service}</label><span className={styles.connectionBadge}>{project.urls?.[service] ? 'URL 저장됨' : '미연결'}</span></div>
            <input id={'settings-url-' + service} type="url" inputMode="url" autoComplete="off" spellCheck={false}
              className={form.input} placeholder={service + ' URL 입력'} value={draft[service]}
              onChange={event => { setDraft(current => ({ ...current, [service]: event.target.value })); setError(''); }} />
          </div>
          <div className={styles.serviceActions}>
            <button type="button" className={`${styles.smallButton} ${styles.emphasis}`} onClick={() => void save(service)}>{pending === service ? '저장 중…' : '저장'}</button>
            {project.urls?.[service] && <button type="button" className={`${styles.smallButton} ${styles.disconnect}`} onClick={() => void save(service, true)}>연결 해제</button>}
          </div>
        </li>)}
      </ul>
    </fieldset>
  </section>;
}
