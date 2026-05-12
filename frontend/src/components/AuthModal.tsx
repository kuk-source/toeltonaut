import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { login, register } from '../api/client'
import { saveToken } from '../auth'
import type { CurrentUser } from '../types'

interface Props {
  onSuccess: (user: CurrentUser) => void
  onClose: () => void
}

type Tab = 'login' | 'register'

export default function AuthModal({ onSuccess, onClose }: Props) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const firstInputRef = useRef<HTMLInputElement>(null)

  // Fokus auf erstes Input beim Öffnen
  useEffect(() => {
    firstInputRef.current?.focus()
  }, [])

  // Escape-Taste schließt Modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const tokens = tab === 'login'
        ? await login(email, password)
        : await register(email, password)
      saveToken(tokens.access_token)
      const { getMe } = await import('../api/client')
      const user = await getMe()
      onSuccess(user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unbekannter Fehler')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-vulkan/70 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="bg-lava rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
      >

        {/* Tabs */}
        <div className="flex border-b border-white/10" id="auth-modal-title">
          {(['login', 'register'] as Tab[]).map((tabKey) => (
            <button
              key={tabKey}
              onClick={() => { setTab(tabKey); setError(null) }}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                tab === tabKey
                  ? 'text-gletscherblau border-b-2 border-gletscherblau'
                  : 'text-geysirweiss/40 hover:text-geysirweiss/70'
              }`}
            >
              {tabKey === 'login' ? t('auth.login') : t('auth.register')}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="space-y-3">
            <input
              ref={firstInputRef}
              type="email"
              required
              placeholder={t('auth.email')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-vulkan border border-white/10 rounded-lg px-4 py-2.5 text-geysirweiss placeholder-geysirweiss/30 text-sm focus:outline-none focus:border-gletscherblau/60 transition-colors"
            />
            <input
              type="password"
              required
              placeholder={t('auth.password')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-vulkan border border-white/10 rounded-lg px-4 py-2.5 text-geysirweiss placeholder-geysirweiss/30 text-sm focus:outline-none focus:border-gletscherblau/60 transition-colors"
            />
          </div>

          {error && (
            <p role="alert" className="text-flaggenrot-text text-xs">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-islandblau hover:bg-islandblau/80 disabled:opacity-50 disabled:cursor-not-allowed text-geysirweiss font-medium py-2.5 rounded-lg text-sm transition-colors"
          >
            {loading ? t('auth.loading') : tab === 'login' ? t('auth.login') : t('auth.register')}
          </button>
        </form>
      </div>
    </div>
  )
}
