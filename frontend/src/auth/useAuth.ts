import { useCallback, useEffect, useState } from 'react'
import {
  createCheckout,
  createPortal,
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  type AuthUser,
} from './authApi'

const anonymous: AuthUser = { authenticated: false, is_vip: false }

export function useAuth() {
  const [user, setUser] = useState<AuthUser>(anonymous)
  const [loading, setLoading] = useState(true)
  const [billingNotice, setBillingNotice] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const me = await fetchMe()
      setUser(me)
      return me
    } catch {
      setUser(anonymous)
      return anonymous
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const billing = params.get('billing')
    if (!billing) return

    if (billing === 'success') {
      setBillingNotice('支付成功，正在同步 Pro 权益…')
      let tries = 0
      const timer = window.setInterval(async () => {
        tries += 1
        const me = await refresh()
        if (me.is_vip || tries >= 10) {
          window.clearInterval(timer)
          setBillingNotice(
            me.is_vip ? 'Pro 已生效：AI 总结无限次' : '支付已完成，若权益未显示请稍后刷新',
          )
        }
      }, 1500)
      return () => window.clearInterval(timer)
    }
    if (billing === 'cancel') {
      setBillingNotice('已取消支付')
    }
    if (billing === 'portal') {
      setBillingNotice('已返回订阅管理')
      void refresh()
    }

    const url = new URL(window.location.href)
    url.searchParams.delete('billing')
    window.history.replaceState({}, '', url.pathname + url.search + url.hash)
  }, [refresh])

  const register = useCallback(
    async (email: string, password: string) => {
      const me = await apiRegister(email, password)
      setUser(me)
      return me
    },
    [],
  )

  const login = useCallback(async (email: string, password: string) => {
    const me = await apiLogin(email, password)
    setUser(me)
    return me
  }, [])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(anonymous)
  }, [])

  const startCheckout = useCallback(async () => {
    const url = await createCheckout()
    window.location.href = url
  }, [])

  const openPortal = useCallback(async () => {
    const url = await createPortal()
    window.location.href = url
  }, [])

  return {
    user,
    loading,
    billingNotice,
    clearBillingNotice: () => setBillingNotice(null),
    refresh,
    register,
    login,
    logout,
    startCheckout,
    openPortal,
  }
}

export type AuthController = ReturnType<typeof useAuth>
