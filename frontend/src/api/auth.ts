// Vue 概念：API 模块负责登录、退出和会话检查，页面只处理用户交互。
// Vue 概念：HttpOnly Cookie 由浏览器自动携带，前端无法读取访问密钥。
// Vue 概念：路由守卫依赖会话响应决定是否允许进入业务页面。

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
)
const AUTH_URL = `${API_BASE_URL}/api/auth/session`

export interface AuthSession {
  authenticated: boolean
  auth_required: boolean
}

async function errorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown }
    return typeof payload.detail === 'string' ? payload.detail : fallback
  } catch {
    return fallback
  }
}

export async function fetchAuthSession(): Promise<AuthSession> {
  const response = await fetch(AUTH_URL, { credentials: 'same-origin' })
  if (response.status === 401) {
    return { authenticated: false, auth_required: true }
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response, '认证状态请求失败'))
  }
  return (await response.json()) as AuthSession
}

export async function loginWithApiKey(apiKey: string): Promise<AuthSession> {
  const response = await fetch(AUTH_URL, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response, '访问密钥无效'))
  }
  return (await response.json()) as AuthSession
}

export async function logout(): Promise<void> {
  const response = await fetch(AUTH_URL, {
    method: 'DELETE',
    credentials: 'same-origin',
  })
  if (!response.ok && response.status !== 401) {
    throw new Error(await errorMessage(response, '退出失败'))
  }
}
