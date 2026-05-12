import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteAccount } from '../api/client'
import type { CurrentUser } from '../types'

interface AccountPageProps {
  user: CurrentUser
  onDeleted: () => void
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export default function AccountPage({ user, onDeleted }: AccountPageProps) {
  const { t } = useTranslation()
  const [confirmEmail, setConfirmEmail] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const emailMatches = confirmEmail.trim().toLowerCase() === user.email.toLowerCase()

  const handleDeleteRequest = () => {
    setShowConfirm(true)
    setError(null)
    setConfirmEmail('')
  }

  const handleCancel = () => {
    setShowConfirm(false)
    setConfirmEmail('')
    setError(null)
  }

  const handleConfirmDelete = async () => {
    if (!emailMatches) return
    setLoading(true)
    setError(null)
    try {
      await deleteAccount()
      onDeleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unbekannter Fehler')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl w-full space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-geysirweiss text-2xl font-bold tracking-tight">{t('account.title')}</h2>
        <p className="text-geysirweiss/40 text-sm mt-1">{t('account.subtitle')}</p>
      </div>

      {/* Account-Infos */}
      <div className="bg-lava rounded-xl p-6 space-y-4">
        <div className="space-y-1">
          <label className="text-geysirweiss/45 text-xs uppercase tracking-wider">{t('account.emailLabel')}</label>
          <p className="text-geysirweiss font-medium">{user.email}</p>
        </div>
        <div className="space-y-1">
          <label className="text-geysirweiss/45 text-xs uppercase tracking-wider">{t('account.createdLabel')}</label>
          <p className="text-geysirweiss/80">{formatDate(user.created_at)}</p>
        </div>
      </div>

      {/* Trennlinie */}
      <hr className="border-lava/60" />

      {/* Datenschutz-Sektion */}
      <div className="space-y-4">
        <h3 className="text-geysirweiss/80 font-semibold text-sm uppercase tracking-wider">{t('account.privacy')}</h3>

        {!showConfirm ? (
          <div className="bg-lava rounded-xl p-6 space-y-4">
            <p className="text-geysirweiss/60 text-sm leading-relaxed">
              {t('account.deleteWarning')}
            </p>
            <button
              onClick={handleDeleteRequest}
              className="border border-flaggenrot text-flaggenrot hover:bg-flaggenrot/10 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {t('account.deleteButton')}
            </button>
          </div>
        ) : (
          <div className="bg-lava rounded-xl p-6 space-y-5 border border-flaggenrot/40">
            <div className="space-y-1">
              <p className="text-flaggenrot text-sm font-semibold">{t('account.confirmTitle')}</p>
              <p className="text-geysirweiss/55 text-sm leading-relaxed">
                {t('account.confirmWarning')}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-geysirweiss/60 text-xs">
                {t('account.confirmEmailLabel')}
                <span className="text-geysirweiss/80 font-mono ml-1">{user.email}</span>
              </label>
              <input
                type="email"
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                placeholder={user.email}
                disabled={loading}
                className="w-full bg-vulkan border border-lava/80 focus:border-flaggenrot/60 text-geysirweiss placeholder-geysirweiss/20 rounded-lg px-3 py-2 text-sm outline-none transition-colors disabled:opacity-50"
                autoFocus
              />
            </div>

            {error && (
              <p className="text-flaggenrot text-xs bg-flaggenrot/10 rounded-lg px-3 py-2">{error}</p>
            )}

            <div className="flex gap-3">
              <button
                onClick={handleConfirmDelete}
                disabled={!emailMatches || loading}
                className="bg-flaggenrot hover:bg-flaggenrot/80 disabled:bg-flaggenrot/30 disabled:cursor-not-allowed text-geysirweiss px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <span className="inline-block w-3 h-3 border-2 border-geysirweiss/30 border-t-geysirweiss rounded-full animate-spin" />
                    {t('account.deleting')}
                  </>
                ) : (
                  t('account.confirmDelete')
                )}
              </button>
              <button
                onClick={handleCancel}
                disabled={loading}
                className="text-geysirweiss/50 hover:text-geysirweiss/80 px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
              >
                {t('account.cancel')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
