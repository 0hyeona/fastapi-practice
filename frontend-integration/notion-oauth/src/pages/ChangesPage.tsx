import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';
import closeIcon from '../../assets/icons/close.svg';
import { services, type Change, type Service } from '../data/projects';
import { useProjects } from '../state/ProjectsContext';
import type { FilterOption } from '../components/FilterSelect';
import { MoodFilter } from '../components/MoodFilter';
import { DateRangeFilter, type DateRange } from '../components/DateRangeFilter';
import { SearchField } from '../components/SearchField';
import { SelectedChangeCard } from '../components/SelectedChangeCard';
import { Badge, PageHeading, ServiceIcon, useDocumentTitle } from '../components/ui';
import form from '../components/form.module.css';
import ui from '../components/ui.module.css';
import styles from './ChangesPage.module.css';

const serviceOptions: readonly FilterOption<Service | 'all'>[] = [
  { value: 'all', label: '서비스 전체' },
  ...services.map((service) => ({ value: service, label: service })),
];

function isService(value: string | null): value is Service {
  return services.some((service) => service === value);
}

function dateKey(date: Date) {
  return [date.getFullYear(), String(date.getMonth()+1).padStart(2,'0'), String(date.getDate()).padStart(2,'0')].join('.');
}
function initialPeriod(params: URLSearchParams): DateRange | null {
  if (!['today', 'week'].includes(params.get('period') ?? '')) return null;
  const end = new Date(); const start = new Date();
  if (params.get('period') === 'week') start.setDate(start.getDate()-6);
  return { start: dateKey(start), end: dateKey(end) };
}
function inPeriod(change: Change, period: DateRange | null) {
  if (!period) return true;
  if (!Number.isFinite(change.daysAgo)) return false;
  const date = new Date(); date.setDate(date.getDate()-change.daysAgo);
  const key = dateKey(date); return key >= period.start && key <= period.end;
}

function checkboxId(change: Change) {
  return `change-${change.id}-check`;
}

function matchesQuery(change: Change, query: string) {
  if (!query) return true;
  return [change.title, change.description, change.service, change.status, change.meta, change.reference]
    .some((text) => text.toLowerCase().includes(query));
}

export function ChangesPage() {
  useDocumentTitle('변경사항 선택');
  const { activeProject: project, selectedChangeIds, toggleChange, analyze, analyzing, analysisError, cancelAnalysis, activityStates, refreshActivities, figma } = useProjects();
  const navigate = useNavigate();
  useEffect(() => () => cancelAnalysis(), [cancelAnalysis]);
  const [searchParams, setSearchParams] = useSearchParams();
  const serviceParam = searchParams.get('service');
  const service = isService(serviceParam) ? serviceParam : 'all';
  const { reload: reloadFigma } = figma;
  useEffect(() => {
    if (service === 'all' || service === 'Figma') return reloadFigma();
  }, [reloadFigma, service]);
  const [query, setQuery] = useState('');
  const [period, setPeriod] = useState<DateRange | null>(() => initialPeriod(searchParams));
  const [status, setStatus] = useState('all');
  const [hiddenIds, setHiddenIds] = useState<string[]>([]);
  const restoreButton = useRef<HTMLButtonElement>(null);
  const emptyMessage = useRef<HTMLParagraphElement>(null);
  const selectedHeading = useRef<HTMLHeadingElement>(null);
  const selectedList = useRef<HTMLUListElement>(null);
  // 누른 버튼이 사라지는 동작(숨기기, 다시 보기, 선택 해제, 필터 초기화) 뒤에 포커스를 옮길 곳을 렌더링 후에 찾습니다.
  const pendingFocus = useRef<(() => HTMLElement | null | undefined) | null>(null);
  useEffect(() => {
    if (!pendingFocus.current) return;
    const target = pendingFocus.current();
    pendingFocus.current = null;
    target?.focus();
  });
  if (!project) return <Navigate to="/projects" replace />;

  const visibleServices = services.filter(item => service === 'all' || item === service);
  const waiting = visibleServices.some(item => ['pending', 'loading', 'error', 'disconnected'].includes(activityStates[item].status));
  const statusOptions: FilterOption<string>[] = [
    { value: 'all', label: '상태 전체' },
    { value: '초안', label: '초안' }, { value: '진행중', label: '진행 중' }, { value: '완료', label: '완료' },
  ];

  const normalizedQuery = query.trim().toLowerCase();
  const hiddenChanges = project.changes.filter((change) => hiddenIds.includes(change.id));
  const matchesFilters = (change: Change) => (
    inPeriod(change, period)
    && (service === 'all' || change.service === service)
    && (status === 'all' || change.status.replace(/\s/g, '') === status)
    && matchesQuery(change, normalizedQuery)
  );
  const shownChanges = project.changes.filter((change) => !hiddenIds.includes(change.id));
  const visibleChanges = shownChanges.filter(matchesFilters);
  const hasServiceChanges = project.changes.some(change => service === 'all' || change.service === service);
  const filteredOutCount = shownChanges.length - visibleChanges.length;
  // 오른쪽 패널은 고른 순서대로 보여줍니다.
  const selectedChanges = selectedChangeIds
    .map((id) => project.changes.find((change) => change.id === id))
    .filter((change): change is Change => !!change);

  function changeService(value: Service | 'all') {
    setSearchParams(value === 'all' ? {} : { service: value }, { replace: true });
  }

  function focusCheckbox(change: Change | undefined) {
    return change ? document.getElementById(checkboxId(change)) : null;
  }

  function hideChange(change: Change) {
    const index = visibleChanges.indexOf(change);
    const next = visibleChanges[index + 1] ?? visibleChanges[index - 1];
    pendingFocus.current = () => focusCheckbox(next) ?? restoreButton.current;
    setHiddenIds((current) => [...current, change.id]);
    if (selectedChangeIds.includes(change.id)) toggleChange(change.id);
  }

  function restoreHidden() {
    const restored = hiddenChanges.find(matchesFilters);
    pendingFocus.current = () => focusCheckbox(restored ?? visibleChanges[0]) ?? emptyMessage.current;
    setHiddenIds([]);
  }

  function resetFilters() {
    setQuery('');
    setPeriod(null);
    setStatus('all');
    changeService('all');
    pendingFocus.current = () => focusCheckbox(shownChanges[0]);
  }

  function removeSelected(change: Change, index: number) {
    // 다음 카드의 선택 해제 버튼으로, 마지막이면 이전 카드, 모두 비면 패널 제목으로 옮깁니다.
    pendingFocus.current = () => {
      const buttons = selectedList.current?.querySelectorAll('button');
      return buttons?.[Math.min(index, buttons.length - 1)] ?? selectedHeading.current;
    };
    toggleChange(change.id);
  }

  async function startAnalysis() {
    if (analyzing) return;
    const result = await analyze();
    if (result) navigate('/stories/analysis');
  }

  return (
    <div className={styles.page}>
      <PageHeading title="변경사항 선택" />
      <div className={styles.layout}>
        <section className={styles.changes} aria-label="변경사항 목록">
          <div className={styles.toolbar}>
            <SearchField className={styles.search} label="변경사항 검색" placeholder="변경 메시지, 서비스, 상태 검색" value={query} onChange={setQuery} />
            <div className={styles.filters}>
              <DateRangeFilter value={period} onChange={setPeriod} />
              <MoodFilter label="서비스" value={service} options={serviceOptions} onChange={changeService} />
              <MoodFilter label="상태" value={status} options={statusOptions} onChange={setStatus} />
            </div>
          </div>

          {hiddenChanges.length > 0 && (
            <button ref={restoreButton} type="button" className={styles.restore} onClick={restoreHidden}>
              숨긴 변경사항 {hiddenChanges.length}개 다시 보기
            </button>
          )}

          {visibleServices.map(item => {
            const state = activityStates[item];
            if (state.status === 'ready' && item === 'GitHub') return null;
            if (item === 'Figma' && state.status !== 'disconnected') {
              const count = project.changes.filter(change => change.service === 'Figma').length;
              return <div key={item} className={`${styles.serviceNotice} ${state.status === 'error' || figma.error ? styles.serviceError : ''}`}>
                <div className={styles.noticeIcon}><ServiceIcon service={item} /></div>
                <div className={styles.noticeContent}>
                  <div className={styles.noticeTitle}><strong>Figma</strong><span role="status">
                    {figma.syncing ? '수집 중…' : state.status === 'loading' ? '저장된 변경사항 조회 중…' : state.status === 'error' ? '조회 실패' : '저장된 변경사항'}
                  </span></div>
                  {(state.status === 'ready' || count > 0) && <p>미정리 변경사항 {count}개</p>}
                  {state.status === 'error' && <p role="alert">{state.error}</p>}
                  {figma.notice && <p role={figma.error ? 'alert' : 'status'}>{figma.notice}</p>}
                  {figma.hasMore && <p>새로고침하면 다음 페이지의 기록을 수집해요.</p>}
                </div>
                <div className={styles.noticeActions}>
                  <button type="button" className={styles.textButton} disabled={figma.refreshDisabled} onClick={figma.refresh}>새로고침</button>
                  {state.status === 'error' && <button type="button" className={styles.textButton} disabled={figma.syncing} onClick={figma.reload}>목록 다시 조회</button>}
                </div>
              </div>;
            }
            return <div key={item} className={`${styles.serviceNotice} ${state.status === 'error' ? styles.serviceError : ''}`} role={state.status === 'error' ? 'alert' : 'status'}>
              <div className={styles.noticeIcon}><ServiceIcon service={item} /></div>
              <div className={styles.noticeContent}><div className={styles.noticeTitle}><strong>{item}</strong><span>{state.status === 'error' ? '불러오기 실패' : state.status === 'disconnected' ? '연결 필요' : state.status === 'ready' ? '수집 완료' : '불러오는 중'}</span></div>
              <p>{state.status === 'loading' ? '변경사항을 수집·조회하고 있어요…' : state.status === 'pending' ? '변경사항 조회를 준비하고 있어요.' : state.status === 'disconnected' ? '서비스를 연결하면 변경사항을 모아볼 수 있어요.' : state.status === 'ready' ? `미정리 변경사항 ${project.changes.filter(change => change.service === item).length}개` : state.error}</p></div>
              {item === 'Notion' && state.status === 'error' && <Link className={styles.textButton} to="/settings#notion-account">Notion 연결 설정</Link>}
              {item !== 'Figma' && state.status === 'error' && <button type="button" className={styles.textButton} onClick={() => refreshActivities(item)}>다시 시도</button>}
              {item === 'Notion' && (state.status === 'ready' || state.status === 'loading') && <button type="button" className={styles.textButton} disabled={state.status === 'loading'} onClick={() => refreshActivities(item)}>새로고침</button>}
              {state.status === 'disconnected' && <Link className={styles.textButton} to={'/settings#settings-url-' + item}>연결하기</Link>}
            </div>;
          })}
          {visibleChanges.length === 0 && waiting && !hasServiceChanges ? null : !hasServiceChanges ? (
            <div className={styles.empty}>
              <p>아직 수집된 변경사항이 없어요.</p>
              <Link to="/stories/new" className={styles.textButton}>Story 직접 작성하기</Link>
            </div>
          ) : visibleChanges.length === 0 ? (
            <div className={styles.empty}>
              <p ref={emptyMessage} tabIndex={-1}>조건에 맞는 변경사항이 없어요.</p>
              {filteredOutCount > 0 && (
                <>
                  <p className={styles.emptyHint}>필터나 검색어에 가려진 변경사항이 {filteredOutCount}개 있어요.</p>
                  <button type="button" className={styles.textButton} onClick={resetFilters}>필터 초기화</button>
                </>
              )}
            </div>
          ) : (
            <ul className={styles.feed}>
              {visibleChanges.map((change) => (
                <li key={change.id}>
                  <FeedCard
                    change={change}
                    selected={selectedChangeIds.includes(change.id)}
                    disabled={analyzing}
                    onToggle={() => toggleChange(change.id)}
                    onHide={() => hideChange(change)}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className={styles.side}>
          <section className={`${styles.panel} ${styles.selectedPanel}`} aria-labelledby="selected-heading">
            <h2 id="selected-heading" ref={selectedHeading} tabIndex={-1}>선택된 변경사항</h2>
            {selectedChanges.length > 0 ? (
              <ul ref={selectedList} className={styles.selectedList}>
                {selectedChanges.map((change, index) => (
                  <li key={change.id} className={styles.selectedItem}>
                    <SelectedChangeCard change={change} onRemove={() => removeSelected(change, index)} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.empty}>왼쪽에서 Story로 정리할 변경사항을 선택해주세요.</p>
            )}
          </section>

          <p role="status">변경사항은 최대 20개까지 선택할 수 있어요. ({selectedChanges.length}/20)</p>
          {analysisError && <p role="alert">{analysisError}</p>}

          <button type="button" className={`${ui.primaryButton} ${styles.analyzeButton}`} disabled={analyzing || selectedChanges.length === 0 || selectedChanges.length > 20} onClick={startAnalysis}>
            {analyzing ? 'AI 분석 중…' : 'AI Story 분석'}
          </button>
        </div>
      </div>
    </div>
  );
}

type FeedCardProps = {
  change: Change;
  selected: boolean;
  disabled?: boolean;
  onToggle: () => void;
  onHide: () => void;
};

// 카드 전체가 체크박스의 label이라 어디를 눌러도 선택됩니다. 숨기기 버튼은 label 밖에 겹쳐 둡니다.
function FeedCard({ change, selected, disabled, onToggle, onHide }: FeedCardProps) {
  const titleId = `change-${change.id}-title`;
  const metaId = `change-${change.id}-meta`;
  return (
    <div className={styles.card}>
      <label className={styles.cardBody}>
        <span className={styles.cardHeader}>
          <ServiceIcon service={change.service} />
          <span className={styles.source}>
            <span className={styles.service}>{change.service}</span>
            <span id={metaId} className={styles.meta}>{change.meta}</span>
          </span>
          <input
            id={checkboxId(change)}
            type="checkbox"
            className={`${form.radio} ${styles.check}`}
            disabled={disabled}
            checked={selected}
            onChange={onToggle}
            aria-labelledby={titleId}
            aria-describedby={metaId}
          />
        </span>
        <span id={titleId} className={styles.title}>{change.title}</span>
        <span className={styles.description}>{change.description}</span>
        <span className={styles.status}><Badge>{change.status}</Badge></span>
      </label>
      <button type="button" className={styles.hide} disabled={disabled} onClick={onHide} aria-label={`${change.title} 목록에서 숨기기`}>
        <img src={closeIcon} alt="" width="24" height="24" />
      </button>
    </div>
  );
}
