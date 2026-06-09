import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api'
import type { LoginRequest, UserInfo } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const refreshToken = ref<string>(localStorage.getItem('refresh_token') || '')

  const isLoggedIn = () => !!token.value
  const isGroup = () => user.value?.role === 'group'
  const isEcovacs = () => user.value?.role === 'ecovacs'
  const isTineco = () => user.value?.role === 'tineco'

  async function login(data: LoginRequest) {
    const res = await authApi.login(data)
    token.value = res.data.access_token
    refreshToken.value = res.data.refresh_token
    localStorage.setItem('access_token', res.data.access_token)
    localStorage.setItem('refresh_token', res.data.refresh_token)
    await fetchUser()
  }

  async function fetchUser() {
    try {
      const res = await authApi.me()
      user.value = res.data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
  }

  return { user, token, isLoggedIn, isGroup, isEcovacs, isTineco, login, fetchUser, logout }
})
