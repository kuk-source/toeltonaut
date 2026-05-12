import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { adminResetAll, getAdminBackupFullUrl, getAdminBackupLearnedUrl } from '../api/client'
import LernStatus from './LernStatus'
import TrainingManager from './TrainingManager'

interface Props {
  onReset: () => void
}

export default function AdminPanel({ onReset }: Props) {
  const { t } = useTranslation()
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleReset = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await adminResetAll()
      setShowConfirm(false)
      setResult(t('admin.resultOk', { videos: r.deleted_videos, files: r.deleted_files }))
      onReset()
    } catch (e) {
      setShowConfirm(false)
      setError(e instanceof Error ? e.message : t('admin.resultError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <LernStatus />
      <TrainingManager />

      <hr className="border-lava/40 my-2" />

      <div className="space-y-4">
        <h3 className="text-geysirweiss/50 text-xs uppercase tracking-widest font-semibold">{t('admin.dbTitle')}</h3>

        <div className="rounded-xl border border-lava bg-lava/40 divide-y divide-lava">

          {/* Vollständiges Backup */}
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-geysirweiss text-sm">{t('admin.backupFull')}</p>
              <p className="text-geysirweiss/40 text-xs mt-0.5">
                {t('admin.backupFullDesc')}
              </p>
            </div>
            <a
              href={getAdminBackupFullUrl()}
              download
              className="ml-4 shrink-0 text-xs px-3 py-1.5 rounded-lg border border-gletscherblau/40 text-gletscherblau/80 hover:bg-gletscherblau/10 hover:border-gletscherblau transition-colors"
            >
              {t('admin.download')}
            </a>
          </div>

          {/* Gelerntes Backup */}
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-geysirweiss text-sm">{t('admin.backupLearned')}</p>
              <p className="text-geysirweiss/40 text-xs mt-0.5">
                {t('admin.backupLearnedDesc')}
              </p>
            </div>
            <a
              href={getAdminBackupLearnedUrl()}
              download
              className="ml-4 shrink-0 text-xs px-3 py-1.5 rounded-lg border border-nordlicht/40 text-nordlicht/80 hover:bg-nordlicht/10 hover:border-nordlicht transition-colors"
            >
              {t('admin.download')}
            </a>
          </div>

          {/* DB leeren */}
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-geysirweiss text-sm">{t('admin.resetAll')}</p>
              <p className="text-geysirweiss/40 text-xs mt-0.5">
                {t('admin.resetAllDesc')}
              </p>
            </div>
            <button
              onClick={() => { setResult(null); setError(null); setShowConfirm(true) }}
              className="ml-4 shrink-0 text-xs px-3 py-1.5 rounded-lg border border-flaggenrot/50 text-flaggenrot/80 hover:bg-flaggenrot/10 hover:border-flaggenrot transition-colors"
            >
              {t('admin.clearDb')}
            </button>
          </div>

        </div>

        {result && <p className="text-nordlicht/80 text-sm px-1">{result}</p>}
        {error  && <p className="text-flaggenrot  text-sm px-1">{error}</p>}
      </div>

      {/* Bestätigungs-Modal */}
      {showConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-vulkan/80 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget && !loading) setShowConfirm(false) }}
        >
          <div className="bg-lava rounded-2xl shadow-2xl w-full max-w-sm mx-4">
            <div className="px-6 py-5 space-y-4">
              <div className="flex items-start gap-3">
                <span className="text-flaggenrot text-2xl leading-none mt-0.5">⚠</span>
                <div>
                  <h2 className="text-geysirweiss font-semibold text-base">{t('admin.confirmTitle')}</h2>
                  <p className="text-geysirweiss/55 text-sm mt-1 leading-relaxed">
                    {t('admin.confirmText')}
                  </p>
                </div>
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  onClick={() => void handleReset()}
                  disabled={loading}
                  className="flex-1 py-2.5 rounded-lg bg-flaggenrot hover:bg-flaggenrot/80 disabled:opacity-50 disabled:cursor-not-allowed text-geysirweiss font-medium text-sm transition-colors"
                >
                  {loading ? t('admin.deleting') : t('admin.confirmYes')}
                </button>
                <button
                  onClick={() => setShowConfirm(false)}
                  disabled={loading}
                  className="flex-1 py-2.5 rounded-lg border border-lava/80 text-geysirweiss/50 hover:text-geysirweiss/80 hover:border-geysirweiss/20 disabled:opacity-50 text-sm transition-colors"
                >
                  {t('admin.cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
