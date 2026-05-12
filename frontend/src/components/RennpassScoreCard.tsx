import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getRennpassScore } from '../api/client'
import type { RennpassError, RennpassScoreData } from '../types'

interface Props {
  jobId: string
  speedMs?: number | null
}

function gradeColor(feifGrade: string, score: number): string {
  if (feifGrade === '–') return 'text-geysirweiss/40'
  if (score >= 8.0) return 'text-nordlicht'
  if (score >= 6.0) return 'text-gletscherblau'
  return 'text-flaggenrot'
}

function speedColor(speedMs: number): string {
  if (speedMs >= 8.0) return '#00C896'  // Nordlicht-Grün – Rennpass klar erkennbar
  if (speedMs >= 5.0) return '#F0F4F8'  // Geysir-Weiß – mittlerer Bereich
  return '#C8102E'                       // Flaggenrot – zu langsam für Rennpass
}

function severityClass(severity: RennpassError['severity']): string {
  switch (severity) {
    case 'schwer': return 'bg-flaggenrot/20 text-flaggenrot border border-flaggenrot/30'
    case 'mittel': return 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30'
    case 'leicht': return 'bg-geysirweiss/10 text-geysirweiss/60 border border-geysirweiss/20'
  }
}

function Skeleton() {
  return (
    <div className="bg-lava rounded-2xl p-6 space-y-4 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-5 w-40 bg-geysirweiss/10 rounded" />
        <div className="h-8 w-16 bg-geysirweiss/10 rounded" />
      </div>
      <div className="space-y-2">
        <div className="h-3 w-44 bg-geysirweiss/10 rounded" />
        <div className="h-2 w-full bg-geysirweiss/10 rounded-full" />
      </div>
      <div className="h-4 w-32 bg-geysirweiss/10 rounded" />
    </div>
  )
}

export default function RennpassScoreCard({ jobId, speedMs }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<RennpassScoreData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getRennpassScore(jobId)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((err: unknown) => {
        if (cancelled) return
        setLoading(false)
        const s = (err as { status?: number }).status
        setError(s === 404 ? '404' : 'other')
      })
    return () => { cancelled = true }
  }, [jobId])

  if (loading) return <Skeleton />

  if (error === '404') {
    return (
      <div className="bg-lava rounded-2xl p-6 text-geysirweiss/50 text-sm">
        {t('rennpass.notAvailable404')}
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-lava rounded-2xl p-6 text-flaggenrot text-sm">
        {t('rennpass.loadError')}
      </div>
    )
  }

  if (!data) return null

  const noData = data.feif_grade === '–'
  const scoreColor = gradeColor(data.feif_grade, data.score)
  const syncPct = Math.round(data.lateral_sync * 100)

  return (
    <div className="bg-lava rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-geysirweiss font-semibold text-base">{t('rennpass.title')}</h3>
        <div className={`text-right shrink-0 ${scoreColor}`}>
          {noData ? (
            <span className="text-sm">{t('rennpass.noData')}</span>
          ) : (
            <span className="text-3xl font-bold tabular-nums">{data.feif_grade}</span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-geysirweiss/60">{t('rennpass.lateralSync')}</span>
          <span className="text-geysirweiss/80 tabular-nums">
            {syncPct}%
            <span className="text-geysirweiss/40 ml-2">{t('rennpass.stepsDetected', { count: data.stride_count })}</span>
          </span>
        </div>
        <div className="w-full bg-vulkan rounded-full h-2 overflow-hidden">
          <div
            className="bg-gradient-to-r from-islandblau to-nordlicht h-2 rounded-full transition-all duration-700"
            style={{ width: `${syncPct}%` }}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 text-sm">
        <span className="text-geysirweiss/60">{t('rennpass.suspension')}</span>
        {data.suspension_detected ? (
          <span className="text-nordlicht font-semibold">{t('rennpass.suspensionYes')}</span>
        ) : (
          <span className="text-flaggenrot font-semibold">{t('rennpass.suspensionNo')}</span>
        )}
      </div>

      {speedMs != null && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-sm">
            <span className="text-geysirweiss/60">{t('rennpass.speed')}</span>
            <span className="tabular-nums font-semibold" style={{ color: speedColor(speedMs) }}>
              {(speedMs * 3.6).toFixed(1)} km/h
            </span>
          </div>
          {speedMs < 5.0 && (
            <p className="text-yellow-300 text-xs bg-yellow-500/10 border border-yellow-500/25 rounded-lg px-3 py-1.5">
              {t('rennpass.speedTooSlow')}
            </p>
          )}
        </div>
      )}

      <div className="space-y-2">
        {data.errors.length === 0 ? (
          <p className="text-nordlicht text-sm font-medium">{t('rennpass.noErrors')}</p>
        ) : (
          <ul className="space-y-2">
            {data.errors.map((err, i) => (
              <li key={i} className={`flex items-start gap-3 rounded-lg px-3 py-2 text-sm ${severityClass(err.severity)}`}>
                <span className="shrink-0 font-semibold capitalize">{err.type.replace(/_/g, ' ')}</span>
                <span className="text-xs opacity-80 mt-px">{err.description}</span>
                <span className="ml-auto shrink-0 font-mono text-xs opacity-60">
                  Fr.{err.frame_range[0]}–{err.frame_range[1]}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

    </div>
  )
}
