import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getLearningStatus } from '../api/client'
import type { LearningStatus } from '../types'

export default function LernStatus() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<LearningStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getLearningStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="rounded-xl border border-geysirweiss/10 bg-lava p-5 text-geysirweiss/30 text-sm">
        {t('lernStatus.loading')}
      </div>
    )
  }

  if (!status) {
    return (
      <div className="rounded-xl border border-geysirweiss/10 bg-lava p-5 text-geysirweiss/30 text-sm">
        {t('lernStatus.notAvailable')}
      </div>
    )
  }

  const gaits = Object.entries(status.gait_distribution).sort((a, b) => b[1] - a[1])

  return (
    <div className="rounded-xl border border-geysirweiss/10 bg-lava overflow-hidden">
      <div className="px-5 py-3.5 border-b border-geysirweiss/10">
        <h3 className="text-geysirweiss font-semibold text-sm">{t('lernStatus.title')}</h3>
        <p className="text-geysirweiss/35 text-xs mt-0.5">
          {t('lernStatus.activeModel')} <span className="text-gletscherblau font-mono">{status.model_version}</span>
        </p>
      </div>

      <div className="p-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label={t('lernStatus.totalVideos')} value={status.total_videos} />
        <Stat label={t('lernStatus.trainingVideos')} value={status.training_videos} highlight />
        <Stat label={t('lernStatus.totalFrames')} value={status.total_frames.toLocaleString('de')} />
        <Stat label={t('lernStatus.annotatedFrames')} value={status.annotated_frames} highlight={status.annotated_frames > 0} />
      </div>

      {gaits.length > 0 && (
        <div className="px-5 pb-5">
          <p className="text-geysirweiss/40 text-xs uppercase tracking-wider font-medium mb-2">{t('lernStatus.gaitsLabel')}</p>
          <div className="flex flex-wrap gap-2">
            {gaits.map(([gait, count]) => (
              <span key={gait} className="inline-flex items-center gap-1.5 bg-islandblau/20 rounded-lg px-2.5 py-1 text-xs text-gletscherblau">
                {gait}
                <span className="text-geysirweiss/50 font-mono">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, highlight = false }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div>
      <p className="text-geysirweiss/35 text-xs mb-0.5">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${highlight ? 'text-nordlicht' : 'text-geysirweiss'}`}>
        {value}
      </p>
    </div>
  )
}
