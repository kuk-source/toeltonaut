import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { updateVideoMetadata } from '../api/client'
import type { VideoEntry } from '../types'

interface Props {
  entry: VideoEntry
  onSave: (updated: Partial<VideoEntry>) => void
  onClose: () => void
}

const GAIT_OPTIONS = ['', 'Tölt', 'Trab', 'Schritt', 'Galopp', 'Rennpass', 'Gemischt'] as const

const inputClass =
  'w-full bg-vulkan border border-lava rounded-lg px-3 py-2 text-geysirweiss text-sm placeholder-geysirweiss/30 focus:outline-none focus:border-gletscherblau transition-colors'

export default function MetadataEditModal({ entry, onSave, onClose }: Props) {
  const { t } = useTranslation()
  const [horseName, setHorseName] = useState(entry.horse_name ?? '')
  const [gaitLabel, setGaitLabel] = useState(entry.gait_label ?? '')
  const [trainingConsent, setTrainingConsent] = useState(entry.training_consent ?? false)
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

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data: Parameters<typeof updateVideoMetadata>[1] = {}
      if (horseName !== (entry.horse_name ?? ''))       data.horse_name      = horseName
      if (gaitLabel !== (entry.gait_label ?? ''))       data.gait_label      = gaitLabel
      if (trainingConsent !== (entry.training_consent ?? false)) data.training_consent = trainingConsent

      if (Object.keys(data).length > 0) {
        await updateVideoMetadata(entry.job_id, data)
      }

      const updated: Partial<VideoEntry> = {
        horse_name:       horseName || undefined,
        gait_label:       gaitLabel || undefined,
        training_consent: trainingConsent,
        is_training_contribution: trainingConsent ? true : entry.is_training_contribution,
      }
      onSave(updated)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen')
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
        aria-labelledby="metadata-modal-title"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <h2 id="metadata-modal-title" className="text-geysirweiss font-semibold text-sm">{t('metadata.title')}</h2>
          <button
            onClick={onClose}
            className="text-geysirweiss/40 hover:text-geysirweiss/80 transition-colors text-lg leading-none"
            aria-label={t('metadata.close')}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSave} className="p-6 space-y-4">
          <div className="space-y-3">
            <div>
              <label className="block text-geysirweiss/50 text-xs mb-1">{t('metadata.horseName')}</label>
              <input
                ref={firstInputRef}
                type="text"
                value={horseName}
                onChange={(e) => setHorseName(e.target.value)}
                placeholder={t('metadata.horseNamePlaceholder')}
                className={inputClass}
              />
            </div>

            <div>
              <label className="block text-geysirweiss/50 text-xs mb-1">{t('metadata.gait')}</label>
              <select
                value={gaitLabel}
                onChange={(e) => setGaitLabel(e.target.value)}
                className={inputClass}
              >
                {GAIT_OPTIONS.map((g) => (
                  <option key={g} value={g}>{g === '' ? t('metadata.gaitNotSpecified') : g}</option>
                ))}
              </select>
            </div>

            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={trainingConsent}
                onChange={(e) => setTrainingConsent(e.target.checked)}
                className="mt-0.5 accent-nordlicht"
              />
              <span className="text-geysirweiss/60 text-xs group-hover:text-geysirweiss/80 transition-colors">
                {t('metadata.trainingConsent')}
              </span>
            </label>
          </div>

          {error && (
            <p role="alert" className="text-flaggenrot-text text-xs">{error}</p>
          )}

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-islandblau hover:bg-islandblau/80 disabled:opacity-50 disabled:cursor-not-allowed text-geysirweiss font-medium py-2.5 rounded-lg text-sm transition-colors"
            >
              {loading ? t('metadata.saving') : t('metadata.save')}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 border border-lava/80 text-geysirweiss/50 hover:text-geysirweiss/80 hover:border-geysirweiss/20 disabled:opacity-50 py-2.5 rounded-lg text-sm transition-colors"
            >
              {t('metadata.cancel')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
