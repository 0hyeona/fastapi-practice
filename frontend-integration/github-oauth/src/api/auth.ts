import { apiRequest } from './client';

export type LoginRequest = { email: string; password: string };
type LoginResponse = { access_token: string; token_type: string };

const TOKEN_KEY = 'moeum.access_token';

export type AuthUser = {
  id: number; user_id: string; name: string; email: string;
  account_status: string; created_at: string;
};
export type SignupRequest = { user_id: string; name: string; email: string; password: string };
type MessageResponse = { message: string };
type CodeResponse = { reset_token: string; expires_in: number };

function post<T>(path: string, data: unknown): Promise<T> {
  return apiRequest<T>(`/api/auth${path}`, { method: 'POST', body: JSON.stringify(data) });
}

export const signup = (data: SignupRequest) => post<AuthUser>('/signup', data);
export const checkEmail = (email: string) => post<MessageResponse>('/password/check-email', { email });
export const requestPasswordCode = (email: string) => post<MessageResponse>('/password/request-code', { email });
export const verifyPasswordCode = (email: string, code: string) => post<CodeResponse>('/password/verify-code', { email, code });
export const resetPassword = (reset_token: string, new_password: string, confirm_password: string) =>
  post<MessageResponse>('/password/reset', { reset_token, new_password, confirm_password });

function authorization(): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error('로그인이 필요합니다.');
  return { Authorization: `Bearer ${token}` };
}

export function getCurrentUser(signal?: AbortSignal): Promise<AuthUser> {
  return apiRequest('/api/auth/me', { headers: authorization(), signal });
}

export async function logout(): Promise<void> {
  await apiRequest<void>('/api/auth/logout', { method: 'POST', headers: authorization() });
  clearAccessToken();
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

// 서버 검증 응답에서 확인한 email 필드로 로그인합니다.
export async function login(credentials: LoginRequest): Promise<LoginResponse> {
  const data = await apiRequest<unknown>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  });

  return saveLoginResponse(data);
}

export function startGithubLogin(): void {
  const githubBackendUrl =
    import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, '');

  if (!githubBackendUrl) {
    throw new Error('GitHub 로그인 서버 주소를 설정해주세요.');
  }

  window.location.assign(
    `${githubBackendUrl}/api/auth/github/login`
  );
}

// 같은 콜백 코드를 React StrictMode에서 두 번 교환하지 않습니다.
let githubExchange: { code: string; promise: Promise<LoginResponse> } | undefined;
export function completeGithubLogin(_query: string, fragment = ''): Promise<LoginResponse> {
  const params = new URLSearchParams(fragment.replace(/^#/, ''));
  if (params.has('error')) {
    return Promise.reject(new Error(params.get('message') || 'GitHub 로그인에 실패했습니다.'));
  }
  const code = params.get('login_code');
  if (!code || !/^[A-Za-z0-9_-]{43}$/.test(code)) {
    return Promise.reject(new Error('로그인 완료 코드가 없습니다. GitHub 로그인을 다시 시작해 주세요.'));
  }
  // Share the in-flight exchange across React StrictMode effect replays.
  if (githubExchange?.code === code) return githubExchange.promise;
  const promise = apiRequest<unknown>('/api/auth/github/exchange', {
    method: 'POST',
    body: JSON.stringify({ code }),
    cache: 'no-store',
    signal: AbortSignal.timeout(15000),
  }).then(async data => {
    const result = saveLoginResponse(data);
    try {
      await getCurrentUser(AbortSignal.timeout(15000));
    } catch (cause) {
      clearAccessToken();
      throw cause;
    }
    return result;
  });
  githubExchange = { code, promise };
  return promise;
}

function saveLoginResponse(data: unknown): LoginResponse {

  // 토큰 형식이 다르면 성공 화면으로 이동하지 않습니다.
  if (
    typeof data !== 'object' || data === null ||
    !('access_token' in data) || typeof data.access_token !== 'string' ||
    !data.access_token.trim() ||
    ('token_type' in data &&
      (typeof data.token_type !== 'string' || data.token_type.toLowerCase() !== 'bearer'))
  ) {
    throw new Error('로그인 응답의 access_token 또는 token_type 형식을 확인해주세요. Swagger의 성공 응답과 대조가 필요합니다.');
  }

  const result = { access_token: data.access_token, token_type: 'bearer' };
  try {
    // 비밀번호는 저장하지 않고, 받은 토큰만 현재 탭에 저장합니다.
    sessionStorage.setItem(TOKEN_KEY, result.access_token);
  } catch {
    throw new Error('로그인 정보를 저장하지 못했습니다. 브라우저의 사이트 저장소 설정을 확인해주세요.');
  }
  return result;
}
