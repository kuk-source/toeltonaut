import { useState, useCallback, type DragEvent, type ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { uploadVideo } from '../api/client'
import type { UploadResponse } from '../types'

interface Props {
  onJobStarted: (response: UploadResponse) => void
}

const ALLOWED_TYPES = [
  'video/mp4', 'video/quicktime', 'video/x-msvideo',
  'video/x-matroska', 'video/webm',
]
const ALLOWED_EXT = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
const MAX_MB = 4096

const GAIT_OPTIONS = [
  { value: 'Tölt',     label: 'Tölt' },
  { value: 'Trab',     label: 'Trab' },
  { value: 'Schritt',  label: 'Schritt' },
  { value: 'Galopp',   label: 'Galopp' },
  { value: 'Rennpass', label: 'Rennpass' },
]

interface PendingUpload {
  blob: Blob
  name: string
  size: number
}

export default function TrainingUpload({ onJobStarted }: Props) {
  const { t } = useTranslation()
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<PendingUpload | null>(null)
  const [gaitLabel, setGaitLabel] = useState('')
  const [consent, setConsent] = useState(false)

  const validateFile = (file: File): string | null => {
    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '')
    if (!ALLOWED_TYPES.includes(file.type) && !ALLOWED_EXT.includes(ext)) {
      return t('trainingUpload.errorUnsupported', { exts: ALLOWED_EXT.join(', ') })
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      return t('trainingUpload.errorTooLarge', { maxMb: MAX_MB })
    }
    return null
  }

  // Datei sofort lesen (Brave/Chromium invalidiert File-Handles nach State-Updates)
  const handleFile = useCallback((file: File) => {
    const err = validateFile(file)
    if (err) { setError(err); return }
    setError(null)
    const reader = new FileReader()
    reader.onload = () => {
      const blob = new Blob([reader.result as ArrayBuffer], { type: file.type || 'video/mp4' })
      setPending({ blob, name: file.name, size: file.size })
    }
    reader.onerror = () => setError(t('trainingUpload.errorFileRead'))
    reader.readAsArrayBuffer(file)
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!pending || !gaitLabel || !consent) return
    setUploading(true)
    setUploadPct(0)
    try {
      const response = await uploadVideo(pending.blob, pending.name, (p) => setUploadPct(p), {
        gait_label: gaitLabel,
        is_training_contribution: true,
        training_consent: true,
      })
      onJobStarted(response)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('trainingUpload.errorUploadFailed'))
    } finally {
      setUploading(false)
    }
  }, [pending, gaitLabel, consent, onJobStarted])

  const handleCancel = () => {
    setPending(null)
    setGaitLabel('')
    setConsent(false)
    setError(null)
  }

  const onDrop = useCallback((e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  const onDragOver  = (e: DragEvent<HTMLLabelElement>) => { e.preventDefault(); setIsDragging(true) }
  const onDragLeave = () => setIsDragging(false)

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  const inputClass = [
    'w-full bg-vulkan border border-lava rounded-lg px-3 py-2',
    'text-geysirweiss text-sm placeholder-geysirweiss/30',
    'focus:outline-none focus:border-gletscherblau transition-colors',
  ].join(' ')

  const canSubmit = !!(pending && gaitLabel && consent && !uploading)

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">

      {/* Erklärungstext */}
      <div className="bg-lava/60 border border-islandblau/30 rounded-2xl px-6 py-5 space-y-2">
        <h3 className="text-geysirweiss font-semibold text-base">{t('training.heroTitle')}</h3>
        <p className="text-geysirweiss/60 text-sm leading-relaxed">
          {t('training.heroDescription')}
        </p>
      </div>

      {/* Datei-Auswahl / Upload-Bereich */}
      {!pending && !uploading && (
        <div>
          <label
            className={[
              'flex flex-col items-center justify-center',
              'w-full h-48 rounded-2xl border-2 border-dashed cursor-pointer',
              'transition-all duration-200',
              isDragging
                ? 'border-nordlicht bg-nordlicht/10'
                : 'border-islandblau/60 bg-lava hover:border-gletscherblau hover:bg-lava/80',
            ].join(' ')}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
          >
            <input
              type="file"
              className="hidden"
              accept={ALLOWED_EXT.join(',')}
              onChange={onChange}
            />
            <div className="flex flex-col items-center gap-3 text-center px-6">
              <div className="text-4xl select-none">🎓</div>
              <div className="text-geysirweiss font-medium">
                {isDragging ? t('trainingUpload.dropzoneActive') : t('trainingUpload.dropzoneLabel')}
              </div>
              <div className="text-geysirweiss/50 text-sm">{t('trainingUpload.dropzoneOr')}</div>
              <div className="text-geysirweiss/30 text-xs mt-1">
                {t('trainingUpload.formats', { maxGb: MAX_MB / 1024 })}
              </div>
            </div>
          </label>
        </div>
      )}

      {/* Konfiguration + Zustimmung nach Datei-Auswahl */}
      {pending && !uploading && (
        <div className="bg-lava rounded-2xl border border-islandblau/60 px-6 py-5 space-y-5">
          <div className="flex items-center gap-3">
            <span className="text-2xl select-none">🎓</span>
            <div className="min-w-0">
              <p className="text-geysirweiss text-sm font-medium truncate">{pending.name}</p>
              <p className="text-geysirweiss/40 text-xs">
                {(pending.size / 1024 / 1024).toFixed(1)} MB
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {/* Gangart – Pflichtfeld */}
            <div>
              <label className="block text-geysirweiss/70 text-xs mb-1">
                {t('trainingUpload.gaitLabel')} <span className="text-flaggenrot">{t('trainingUpload.gaitRequired')}</span>
              </label>
              <select
                className={inputClass}
                value={gaitLabel}
                onChange={(e) => setGaitLabel(e.target.value)}
              >
                <option value="">{t('trainingUpload.gaitSelect')}</option>
                {GAIT_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <p className="text-geysirweiss/35 text-xs mt-1">
                {t('trainingUpload.gaitHint')}
              </p>
            </div>

            {/* Lernfreigabe – Pflichtfeld */}
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-lava accent-nordlicht flex-shrink-0"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span className="text-geysirweiss/70 text-sm leading-relaxed group-hover:text-geysirweiss/90 transition-colors">
                {t('trainingUpload.consentLabel')}{' '}
                <span className="text-flaggenrot text-xs">{t('trainingUpload.consentRequired')}</span>
              </span>
            </label>
          </div>

          <div className="flex gap-3 pt-1">
            <button
              onClick={handleCancel}
              className="flex-1 py-2 rounded-lg border border-lava/80 text-geysirweiss/50 hover:text-geysirweiss/80 text-sm transition-colors"
            >
              {t('trainingUpload.cancel')}
            </button>
            <button
              onClick={() => void handleSubmit()}
              disabled={!canSubmit}
              className={[
                'flex-1 py-2 rounded-lg font-medium text-sm transition-colors',
                canSubmit
                  ? 'bg-nordlicht hover:bg-nordlicht/80 text-vulkan'
                  : 'bg-lava/80 text-geysirweiss/30 cursor-not-allowed',
              ].join(' ')}
            >
              {t('trainingUpload.submit')}
            </button>
          </div>
        </div>
      )}

      {/* Upload-Fortschritt */}
      {uploading && (
        <div className="bg-lava rounded-2xl border border-islandblau/40 px-6 py-8 flex flex-col items-center gap-4">
          <div className="text-geysirweiss text-sm">{t('trainingUpload.uploadPct', { pct: uploadPct })}</div>
          <div className="w-full bg-vulkan rounded-full h-2">
            <div
              className="bg-nordlicht h-2 rounded-full transition-all duration-300"
              style={{ width: `${uploadPct}%` }}
            />
          </div>
          <div className="text-geysirweiss/60 text-xs">{t('trainingUpload.uploadHint')}</div>
        </div>
      )}

      {error && (
        <div className="text-flaggenrot text-sm text-center bg-flaggenrot/10 rounded-lg px-4 py-2">
          {error}
        </div>
      )}
    </div>
  )
}
