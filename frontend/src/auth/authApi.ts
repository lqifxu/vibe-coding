export type SubscriptionInfo = {
  status: string
  current_period_end: number
  cancel_at_period_end: boolean
  is_vip: boolean
}

export type AuthUser = {
  authenticated: boolean
  id?: number
  email?: string
  is_vip: boolean
  subscription?: SubscriptionInfo | null
  remaining_summaries?: number | null
  free_daily_summaries?: number
  stripe_configured?: boolean
}

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return res.statusText || '请求失败'
  }
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export async function fetchMe(): Promise<AuthUser> {
  const res = await fetch('/api/auth/me', { credentials: 'include' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function register(email: string, password: string): Promise<AuthUser> {
  const res = await fetch('/api/auth/register', {
    method: 'POST',
    credentials: 'include',
    headers: jsonHeaders,
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return { ...data, authenticated: true }
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: jsonHeaders,
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return { ...data, authenticated: true }
}

export async function logout(): Promise<void> {
  const res = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await readError(res))
}

export async function createCheckout(): Promise<string> {
  const res = await fetch('/api/billing/checkout', {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await readError(res))
  const data = (await res.json()) as { url: string }
  if (!data.url) throw new Error('未返回支付链接')
  return data.url
}

export async function createPortal(): Promise<string> {
  const res = await fetch('/api/billing/portal', {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await readError(res))
  const data = (await res.json()) as { url: string }
  if (!data.url) throw new Error('未返回管理链接')
  return data.url
}
