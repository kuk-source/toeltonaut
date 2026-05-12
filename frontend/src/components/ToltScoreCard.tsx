import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getToltScore } from '../api/client'
import type { ToltError, ToltScoreData } from '../types'

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
  if (speedMs >= 6.5) return '#00C896'  // Nordlicht-Grün – schneller Tölt, plausibel
  if (speedMs >= 3.0) return '#F0F4F8'  // Geysir-Weiß – mittlerer Tölt
  return '#C8102E'                       // Flaggenrot – zu langsam für Tölt
}

function severityClass(severity: ToltError['severity']): string {
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
        <div className="h-5 w-32 bg-geysirweiss/10 rounded" />
        <div className="h-8 w-16 bg-geysirweiss/10 rounded" />
      </div>
      <div className="space-y-2">
        <div className="h-3 w-40 bg-geysirweiss/10 rounded" />
        <div className="h-2 w-full bg-geysirweiss/10 rounded-full" />
      </div>
      <div className="h-4 w-48 bg-geysirweiss/10 rounded" />
    </div>
  )
}

export default function ToltScoreCard({ jobId, speedMs }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<ToltScoreData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [collapsed, setCollapsed] = useState(true)

  useEffect(() => {
    let cancelled = false
    getToltScore(jobId)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((err: unknown) => {
        if (cancelled) return
        setLoading(false)
        const status = (err as { status?: number }).status
        if (status === 404) {
          setError('404')
        } else {
          setError('other')
        }
      })
    return () => { cancelled = true }
  }, [jobId])

  if (loading) return <Skeleton />

  if (error === '404') {
    return (
      <div className="bg-lava rounded-2xl p-6 text-geysirweiss/50 text-sm">
        {t('tolt.notAvailable404')}
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-lava rounded-2xl p-6 text-flaggenrot text-sm">
        {t('tolt.loadError')}
      </div>
    )
  }

  if (!data) return null

  const noData = data.feif_grade === '–'
  const scoreColor = gradeColor(data.feif_grade, data.score)
  const regularityPct = Math.round(data.takt_regularity * 100)

  return (
    <div className="bg-lava rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-geysirweiss font-semibold text-base">{t('tolt.title')}</h3>
        <div className="flex items-center gap-3">
          <div className={`text-right shrink-0 ${scoreColor}`}>
            {noData ? (
              <span className="text-sm">{t('tolt.noData')}</span>
            ) : (
              <span className="text-3xl font-bold tabular-nums">{data.feif_grade}</span>
            )}
          </div>
          <button
            onClick={() => setCollapsed(c => !c)}
            className="text-geysirweiss/40 hover:text-geysirweiss/80 transition-colors text-xs leading-none select-none"
            title={collapsed ? t('tolt.expand') : t('tolt.collapse')}
          >
            {collapsed ? '▼' : '▲'}
          </button>
        </div>
      </div>

      {!collapsed && (<>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-geysirweiss/60">{t('tolt.taktRegularity')}</span>
          <span className="text-geysirweiss/80 tabular-nums">
            {regularityPct}%
            <span className="text-geysirweiss/40 ml-2">{t('tolt.stepsDetected', { count: data.beat_count })}</span>
          </span>
        </div>
        <div className="w-full bg-vulkan rounded-full h-2 overflow-hidden">
          <div
            className="bg-gradient-to-r from-islandblau to-nordlicht h-2 rounded-full transition-all duration-700"
            style={{ width: `${regularityPct}%` }}
          />
        </div>
      </div>

      {(data.lap != null || data.df != null || data.subclassification) && (
        <div className="grid grid-cols-3 gap-3">
          {data.lap != null && (
            <div className="bg-vulkan/60 rounded-xl px-3 py-2.5 text-center">
              <div className="text-geysirweiss/40 text-xs mb-0.5">LAP</div>
              <div className="text-gletscherblau font-semibold tabular-nums text-sm">
                {(data.lap * 100).toFixed(1)}%
              </div>
              <div className="text-geysirweiss/25 text-xs">Lateral Adv.</div>
            </div>
          )}
          {data.df != null && (
            <div className="bg-vulkan/60 rounded-xl px-3 py-2.5 text-center">
              <div className="text-geysirweiss/40 text-xs mb-0.5">DF</div>
              <div className="text-gletscherblau font-semibold tabular-nums text-sm">
                {(data.df * 100).toFixed(1)}%
              </div>
              <div className="text-geysirweiss/25 text-xs">Duty Factor</div>
            </div>
          )}
          {data.subclassification && (
            <div className={`rounded-xl px-3 py-2.5 text-center ${
              data.subclassification === 'correct'
                ? 'bg-nordlicht/10'
                : 'bg-flaggenrot/10'
            }`}>
              <div className="text-geysirweiss/40 text-xs mb-0.5">{t('tolt.subtype')}</div>
              <div className={`font-semibold text-sm ${
                data.subclassification === 'correct'
                  ? 'text-nordlicht'
                  : 'text-flaggenrot'
              }`}>
                {data.subclassification === 'correct'
                  ? t('tolt.subtypeCorrect')
                  : data.subclassification === 'passig'
                  ? t('tolt.subtypePassig')
                  : data.subclassification === 'trabig'
                  ? t('tolt.subtypeTrabig')
                  : data.subclassification}
              </div>
              <div className="text-geysirweiss/25 text-xs">Subtyp</div>
            </div>
          )}
        </div>
      )}

      {speedMs != null && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-sm">
            <span className="text-geysirweiss/60">{t('tolt.speed')}</span>
            <span className="tabular-nums font-semibold" style={{ color: speedColor(speedMs) }}>
              {(speedMs * 3.6).toFixed(1)} km/h
            </span>
          </div>
          {speedMs < 2.0 && (
            <p className="text-yellow-300 text-xs bg-yellow-500/10 border border-yellow-500/25 rounded-lg px-3 py-1.5">
              {t('tolt.speedTooSlow')}
            </p>
          )}
          {data.errors.some(e => e.type.toLowerCase().includes('pass')) && speedMs < 5.0 && (
            <p className="text-yellow-300 text-xs bg-yellow-500/10 border border-yellow-500/25 rounded-lg px-3 py-1.5">
              {t('tolt.speedPassHint')}
            </p>
          )}
        </div>
      )}

      <div className="space-y-2">
        {data.errors.length === 0 ? (
          <p className="text-nordlicht text-sm font-medium">{t('tolt.noErrors')}</p>
        ) : (
          <ul className="space-y-2">
            {data.errors.map((err, i) => (
              <li key={i} className={`flex items-start gap-3 rounded-lg px-3 py-2 text-sm ${severityClass(err.severity)}`}>
                <span className="shrink-0 font-semibold capitalize">{err.type}</span>
                <span className="text-xs opacity-80 mt-px">{err.description}</span>
                <span className="ml-auto shrink-0 font-mono text-xs opacity-60">
                  Fr.{err.frame_range[0]}–{err.frame_range[1]}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {data.disclaimer && (
        <p className="text-geysirweiss/30 text-xs border-t border-geysirweiss/10 pt-3">
          ℹ {data.disclaimer}
        </p>
      )}
      </>)}

    </div>
  )
}
