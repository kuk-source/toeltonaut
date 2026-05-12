import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getGaitSegments } from '../api/client'
import type { GaitSegment } from '../types'

interface Props {
  jobId: string
  onSeek?: (ms: number) => void
}

const GAIT_COLORS: Record<string, string> = {
  'Tölt':     'bg-nordlicht',
  'Trab':     'bg-gletscherblau',
  'Schritt':  'bg-islandblau',
  'Galopp':   'bg-flaggenrot',
  'Rennpass': 'bg-purple-500',
  'Gemischt': 'bg-geysirweiss/40',
  'Unbekannt':'bg-lava',
}

const GAIT_TEXT: Record<string, string> = {
  'Tölt':     'text-vulkan',
  'Trab':     'text-vulkan',
  'Schritt':  'text-geysirweiss',
  'Galopp':   'text-geysirweiss',
  'Rennpass': 'text-geysirweiss',
}

export default function GaitSegmentBar({ jobId, onSeek }: Props) {
  const { t } = useTranslation()
  const [segments, setSegments] = useState<GaitSegment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    getGaitSegments(jobId)
      .then(setSegments)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [jobId])

  if (loading) return (
    <div className="bg-lava rounded-xl px-4 py-3 text-geysirweiss/40 text-sm">
      {t('gaitSegment.loading')}
    </div>
  )

  if (error || segments.length === 0) return null

  const totalMs = segments[segments.length - 1].end_ms - segments[0].start_ms || 1
  const isSingle = segments.length === 1
  const label = isSingle ? t('gaitSegment.singleLabel') : t('gaitSegment.multiLabel')

  return (
    <div className="bg-lava rounded-xl border border-islandblau/40">
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors rounded-xl"
      >
        <span className="text-geysirweiss/50 text-xs">{label}</span>
        <span
          className="text-geysirweiss/30 text-[10px] transition-transform duration-200"
          style={{ display: 'inline-block', transform: collapsed ? 'rotate(0deg)' : 'rotate(180deg)' }}
        >
          ▲
        </span>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-3">
          {isSingle ? (
            <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold
              ${GAIT_COLORS[segments[0].gait] ?? 'bg-lava'}
              ${GAIT_TEXT[segments[0].gait] ?? 'text-geysirweiss'}`}>
              {segments[0].gait}
            </span>
          ) : (
            <>
              {/* Segment-Balken */}
              <div className="flex w-full h-8 rounded-lg overflow-hidden gap-px">
                {segments.map((s, i) => {
                  const widthPct = ((s.end_ms - s.start_ms) / totalMs) * 100
                  const color = GAIT_COLORS[s.gait] ?? 'bg-lava'
                  return (
                    <button
                      key={i}
                      title={`${s.gait} (${formatMs(s.start_ms)}–${formatMs(s.end_ms)})`}
                      className={`${color} flex-none hover:brightness-110 transition-all`}
                      style={{ width: `${widthPct}%`, minWidth: widthPct < 3 ? '4px' : undefined }}
                      onClick={() => onSeek?.(s.start_ms)}
                    />
                  )
                })}
              </div>

              {/* Legende */}
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {[...new Map(segments.map(s => [s.gait, s])).values()].map(s => {
                  const color = GAIT_COLORS[s.gait] ?? 'bg-lava'
                  const frames = segments.filter(x => x.gait === s.gait).reduce((a, x) => a + x.frame_count, 0)
                  const totalFrames = segments.reduce((a, x) => a + x.frame_count, 0)
                  const pct = Math.round((frames / totalFrames) * 100)
                  return (
                    <div key={s.gait} className="flex items-center gap-1.5">
                      <span className={`w-3 h-3 rounded-sm flex-shrink-0 ${color}`} />
                      <span className="text-geysirweiss/70 text-xs">{s.gait}</span>
                      <span className="text-geysirweiss/35 text-xs">{pct}%</span>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}:${String(s % 60).padStart(2, '0')}` : `${s}s`
}
