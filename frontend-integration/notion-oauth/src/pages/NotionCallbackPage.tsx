import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { completeNotionConnection } from '../api/notion';
import { AuthShell } from '../components/AuthUI';
import { useDocumentTitle } from '../components/ui';
import styles from './LoginPage.module.css';

export function NotionCallbackPage() {
  useDocumentTitle('Notion 연결');
  const navigate = useNavigate();
  const [query] = useState(() => window.location.search);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    window.history.replaceState(null, '', window.location.pathname);
    completeNotionConnection(query).then(({ returnTo }) => {
      if (active) navigate(returnTo, { replace: true });
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : 'Notion 연결을 완료하지 못했어요.');
    });
    return () => { active = false; };
  }, [query, navigate]);

  return <AuthShell><section className={styles.card}>
    <h1>Notion 연결</h1>
    {error ? <>
      <p className={styles.error} role="alert">{error}</p>
      <Link className={styles.primaryLink} to="/settings#notion-account">설정으로 돌아가기</Link>
    </> : <p role="status">승인한 페이지를 연결하고 있어요…</p>}
  </section></AuthShell>;
}
