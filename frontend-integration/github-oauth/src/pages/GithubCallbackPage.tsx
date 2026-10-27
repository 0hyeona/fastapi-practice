import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { completeGithubLogin } from '../api/auth';
import { useDocumentTitle } from '../components/ui';
import { AuthShell } from '../components/AuthUI';
import { AuthSkeleton } from '../components/Skeleton';
import styles from './LoginPage.module.css';

export function GithubCallbackPage() {
  useDocumentTitle('GitHub 로그인');
  const navigate = useNavigate();
  const [callback] = useState(() => ({
    query: window.location.search,
    fragment: window.location.hash,
  }));
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    // 인증 코드를 브라우저 주소에 계속 남기지 않습니다.
    window.history.replaceState(null, '', window.location.pathname);
    completeGithubLogin(callback.query, callback.fragment).then(() => {
      if (active) navigate('/dashboard', { replace: true });
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : 'GitHub 로그인에 실패했습니다.');
    });
    return () => { active = false; };
  }, [callback, navigate]);
  return <AuthShell><section className={styles.card}>
    {error ? <><h1>GitHub 로그인</h1><p className={styles.error} role="alert">{error}</p><Link className={styles.primaryLink} to="/login">로그인으로 돌아가기</Link></> : <AuthSkeleton />}
  </section></AuthShell>;
}
