import { useState, useCallback, useRef, type DragEvent, type ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { uploadVideo } from '../api/client'
import type { UploadResponse } from '../types'

interface Props {
  onJobStarted: (response: UploadResponse) => void
}

interface PendingFile {
  blob: Blob
  name: string
  size: number
}

const ALLOWED_EXT = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
const ALLOWED_TYPES = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/webm']
const MAX_MB = 4096

export default function UploadZone({ onJobStarted }: Props) {
  const { t } = useTranslation()
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<PendingFile | null>(null)
  const [horseName, setHorseName] = useState('')
  const [gaitLabels, setGaitLabels] = useState<string[]>([])
  const [trainingConsent, setTrainingConsent] = useState(false)
  const [stockmassCm, setStockmassCm] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const validateFile = (file: File): string | null => {
    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '')
    if (!ALLOWED_TYPES.includes(file.type) && !ALLOWED_EXT.includes(ext))
      return t('trainingUpload.errorUnsupported', { exts: ALLOWED_EXT.join(', ') })
    if (file.size > MAX_MB * 1024 * 1024)
      return t('trainingUpload.errorTooLarge', { maxMb: MAX_MB })
    return null
  }

  // Datei sofort beim Auswählen lesen, solange der User-Gesture-Kontext aktiv ist.
  // Brave/Chromium invalidiert File-Handles nach State-Updates oder Unmount.
  const readFile = useCallback((file: File) => {
    const err = validateFile(file)
    if (err) { setError(err); return }
    setError(null)
    const reader = new FileReader()
    reader.onload = () => {
      const blob = new Blob([reader.result as ArrayBuffer], { type: file.type || 'video/mp4' })
      setPending({ blob, name: file.name, size: file.size })
    }
    reader.onerror = () => setError(t('upload.errorFileRead'))
    reader.readAsArrayBuffer(file)
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!pending) return
    if (trainingConsent && gaitLabels.length === 0) {
      setError(t('upload.gaitRequired'))
      return
    }
    setUploading(true)
    setUploadPct(0)
    setError(null)
    try {
      const parsedStockmass = stockmassCm ? parseInt(stockmassCm, 10) : undefined
      const response = await uploadVideo(pending.blob, pending.name, setUploadPct, {
        horse_name: horseName || undefined,
        gait_label: gaitLabels.length > 0 ? gaitLabels.join(',') : undefined,
        training_consent: trainingConsent || undefined,
        stockmass_cm: parsedStockmass && !isNaN(parsedStockmass) ? parsedStockmass : undefined,
      })
      onJobStarted(response)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('upload.errorUploadFailed'))
    } finally {
      setUploading(false)
    }
  }, [pending, horseName, gaitLabels, trainingConsent, stockmassCm, onJobStarted, t])

  const handleCancel = () => {
    setPending(null)
    setHorseName('')
    setGaitLabels([])
    setTrainingConsent(false)
    setStockmassCm('')
    setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const GAIT_CHECKBOXES = [
    { value: 'Tölt',     labelKey: 'gait.toelt' },
    { value: 'Schritt',  labelKey: 'gait.schritt' },
    { value: 'Trab',     labelKey: 'gait.trab' },
    { value: 'Galopp',   labelKey: 'gait.galopp' },
    { value: 'Rennpass', labelKey: 'gait.rennpass' },
  ]

  const toggleGait = (value: string) => {
    setGaitLabels(prev =>
      prev.includes(value) ? prev.filter(g => g !== value) : [...prev, value]
    )
  }

  const onDrop = useCallback((e: DragEvent<HTMLElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) readFile(file)
  }, [readFile])

  const onDragOver  = (e: DragEvent<HTMLElement>) => { e.preventDefault(); setIsDragging(true) }
  const onDragLeave = () => setIsDragging(false)

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) readFile(file)
  }

  const inputClass = 'w-full bg-vulkan border border-lava rounded-lg px-3 py-2 text-geysirweiss text-sm placeholder-geysirweiss/30 focus:outline-none focus:border-gletscherblau transition-colors'

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      {/* Input bleibt immer im DOM; label htmlFor = echte User-Gesture (Brave-kompatibel) */}
      <input
        ref={fileInputRef}
        id="toeltonaut-upload"
        type="file"
        className="hidden"
        accept={ALLOWED_EXT.join(',')}
        onChange={onChange}
        disabled={uploading}
      />

      {pending && !uploading ? (
        <div className="bg-lava rounded-2xl border border-islandblau/60 px-6 py-5 space-y-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl select-none">🎬</span>
            <div className="min-w-0">
              <p className="text-geysirweiss text-sm font-medium truncate">{pending.name}</p>
              <p className="text-geysirweiss/40 text-xs">{(pending.size / 1024 / 1024).toFixed(1)} MB</p>
            </div>
          </div>

          <div>
            <label className="block text-geysirweiss/60 text-xs mb-1">{t('upload.horseName')}</label>
            <input
              type="text"
              className={inputClass}
              placeholder={t('upload.horseNamePlaceholder')}
              value={horseName}
              onChange={(e) => setHorseName(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-geysirweiss/60 text-xs mb-2">{t('upload.gait')}</label>
            <div className="flex flex-wrap gap-2">
              {GAIT_CHECKBOXES.map(({ value, labelKey }) => {
                const active = gaitLabels.includes(value)
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => toggleGait(value)}
                    className={[
                      'text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors select-none',
                      active
                        ? 'bg-islandblau/30 border-gletscherblau/60 text-geysirweiss'
                        : 'border-geysirweiss/20 text-geysirweiss/50 hover:border-geysirweiss/40 hover:text-geysirweiss/70',
                    ].join(' ')}
                  >
                    {t(labelKey)}
                  </button>
                )
              })}
            </div>
            {trainingConsent && gaitLabels.length === 0 && (
              <p className="text-flaggenrot-text text-xs mt-1.5">{t('upload.gaitRequired')}</p>
            )}
          </div>

          <div>
            <label className="block text-geysirweiss/60 text-xs mb-1">
              {t('upload.stockmass')}
              <span className="ml-1 text-geysirweiss/30">{t('upload.stockmassHint')}</span>
            </label>
            <input
              type="number"
              className={inputClass}
              placeholder={t('upload.stockmassPlaceholder')}
              min={80}
              max={200}
              step={1}
              value={stockmassCm}
              onChange={(e) => setStockmassCm(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-3">
            <input
              id="training-consent"
              type="checkbox"
              className="w-4 h-4 rounded cursor-pointer"
              style={{ accentColor: '#00C896' }}
              checked={trainingConsent}
              onChange={(e) => setTrainingConsent(e.target.checked)}
            />
            <label htmlFor="training-consent" className="text-geysirweiss/60 text-sm cursor-pointer select-none">
              {t('upload.trainingConsent')}
            </label>
          </div>

          <div className="flex gap-3 pt-1">
            <button
              onClick={handleCancel}
              className="flex-1 py-2 rounded-lg border border-lava/80 text-geysirweiss/50 hover:text-geysirweiss/80 text-sm transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={() => void handleSubmit()}
              className="flex-1 py-2 rounded-lg bg-islandblau hover:bg-islandblau/80 text-geysirweiss font-medium text-sm transition-colors"
            >
              {t('upload.submit')}
            </button>
          </div>
        </div>
      ) : (
        <label
          htmlFor="toeltonaut-upload"
          className={[
            'flex flex-col items-center justify-center',
            'w-full h-64 rounded-2xl border-2 border-dashed cursor-pointer',
            'transition-all duration-200',
            isDragging ? 'border-nordlicht bg-nordlicht/10' : 'border-islandblau bg-lava hover:border-gletscherblau hover:bg-lava/80',
            uploading ? 'pointer-events-none opacity-70' : '',
          ].join(' ')}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
        >
          {uploading ? (
            <div className="flex flex-col items-center gap-4 w-full px-12">
              <div className="text-geysirweiss text-sm">{t('upload.uploadPct', { pct: uploadPct })}</div>
              <div className="w-full bg-vulkan rounded-full h-2">
                <div className="bg-nordlicht h-2 rounded-full transition-all duration-300" style={{ width: `${uploadPct}%` }} />
              </div>
              <div className="text-geysirweiss/60 text-xs">{t('upload.uploading')}</div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 text-center px-6">
              <div className="text-5xl select-none">🎬</div>
              <div className="text-geysirweiss font-medium text-lg">
                {isDragging ? t('upload.dropzoneActive') : t('upload.dropzoneLabel')}
              </div>
              <div className="text-geysirweiss/30 text-xs mt-1">
                {t('upload.formats', { maxGb: MAX_MB / 1024 })}
              </div>
            </div>
          )}
        </label>
      )}

      {error && (
        <div role="alert" className="text-flaggenrot-text text-sm text-center bg-flaggenrot/10 rounded-lg px-4 py-2">
          {error}
        </div>
      )}
    </div>
  )
}
