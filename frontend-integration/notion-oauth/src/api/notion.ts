import { apiRequest } from './client';
import { getAccessToken } from './auth';

export type NotionConnection = {
  connected: boolean;
  workspace_id: string | null;
  workspace_name: string | null;
};

const PENDING_KEY = 'moeum.notion.pending';
const CALLBACK_PATH = '/auth/notion/callback';
const PATHS = new Set(['/settings', '/dashboard', '/changes', '/projects']);

function authorization(): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error('로그인 후 Notion 연결을 다시 시작해 주세요.');
  return { Authorization: `Bearer ${token}` };
}

export function notionReturnPath(value = '/settings#notion-account'): string {
  const url = new URL(value, window.location.origin);
  return url.origin === window.location.origin && PATHS.has(url.pathname)
    ? `${url.pathname}${url.search}${url.hash}` : '/settings#notion-account';
}

function connection(data: unknown): NotionConnection {
  if (typeof data !== 'object' || data === null || !('connected' in data)
      || typeof data.connected !== 'boolean'
      || !('workspace_id' in data) || !(data.workspace_id === null || typeof data.workspace_id === 'string')
      || !('workspace_name' in data) || !(data.workspace_name === null || typeof data.workspace_name === 'string')) {
    throw new Error('Notion 연결 상태 응답을 확인하지 못했습니다.');
  }
  return data as NotionConnection;
}

export async function getNotionConnection(signal?: AbortSignal): Promise<NotionConnection> {
  return connection(await apiRequest<unknown>('/api/integrations/notion', {
    headers: authorization(), cache: 'no-store', signal,
  }));
}

export async function startNotionConnection(returnTo?: string): Promise<void> {
  const result = await apiRequest<{ authorization_url: string }>('/api/integrations/notion/authorize', {
    method: 'POST', headers: authorization(), cache: 'no-store', signal: AbortSignal.timeout(30000),
  });
  const url = new URL(result.authorization_url);
  if (url.origin !== 'https://api.notion.com' || url.pathname !== '/v1/oauth/authorize') {
    throw new Error('Notion 승인 주소가 올바르지 않습니다.');
  }
  const state = url.searchParams.get('state');
  const callback = new URL(url.searchParams.get('redirect_uri') || '');
  if (!state || callback.origin !== window.location.origin || callback.pathname !== CALLBACK_PATH) {
    throw new Error('Notion 콜백 주소가 현재 사이트와 다릅니다. 서버의 NOTION_OAUTH_REDIRECT_URI 설정을 확인해 주세요.');
  }
  sessionStorage.setItem(PENDING_KEY, JSON.stringify({ state, returnTo: notionReturnPath(returnTo) }));
  window.location.assign(url.href);
}

let exchange: { state: string; token: string | null; promise: Promise<{ returnTo: string }> } | undefined;

export function completeNotionConnection(query: string): Promise<{ returnTo: string }> {
  const params = new URLSearchParams(query);
  if (params.has('error')) {
    sessionStorage.removeItem(PENDING_KEY);
    return Promise.reject(new Error('Notion 연결 승인이 취소됐어요. 설정에서 다시 연결할 수 있어요.'));
  }
  const code = params.get('code');
  const state = params.get('state');
  const token = getAccessToken();
  // Share the exchange across StrictMode effect replays; never retry a used state.
  if (state && exchange?.state === state && exchange.token === token) return exchange.promise;
  try {
    const headers = authorization();
    const saved = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
    if (!code || !state || saved?.state !== state) {
      throw new Error('Notion 연결 요청을 확인하지 못했습니다. 같은 창에서 연결을 다시 시작해 주세요.');
    }
    const returnTo = notionReturnPath(typeof saved.returnTo === 'string' ? saved.returnTo : undefined);
    const promise = apiRequest<unknown>('/api/integrations/notion/exchange', {
      method: 'POST', headers, body: JSON.stringify({ code, state }),
      cache: 'no-store', signal: AbortSignal.timeout(30000),
    }).then(data => {
      if (!connection(data).connected) throw new Error('Notion 연결을 완료하지 못했습니다.');
      return { returnTo };
    }).finally(() => sessionStorage.removeItem(PENDING_KEY));
    exchange = { state, token, promise };
    return promise;
  } catch (error) {
    return Promise.reject(error);
  }
}
