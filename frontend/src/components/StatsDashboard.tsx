import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { VideoEntry } from '../types'

interface Props {
  videos: VideoEntry[]
}

function isToelt(gait: string): boolean {
  const g = gait.toLowerCase()
  return g === 'tölt' || g === 'toelt' || g === 'tölt'
}

export default function StatsDashboard({ videos }: Props) {
  const { t } = useTranslation()
  const stats = useMemo(() => {
    const total = videos.length
    const done = videos.filter(v => v.status === 'done')
    const doneCount = done.length

    const gaitCounts: Record<string, number> = {}
    for (const v of done) {
      const g = v.gait_detected
      if (g) {
        const key = g.trim()
        gaitCounts[key] = (gaitCounts[key] ?? 0) + 1
      }
    }

    let topGait: string | null = null
    let topCount = 0
    for (const [gait, count] of Object.entries(gaitCounts)) {
      if (count > topCount) {
        topCount = count
        topGait = gait
      }
    }

    const contributions = videos.filter(v => v.training_consent === true).length

    const gaitRows = Object.entries(gaitCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([gait, count]) => ({
        gait,
        count,
        pct: doneCount > 0 ? count / doneCount : 0,
        isToelt: isToelt(gait),
      }))

    return { total, doneCount, topGait, contributions, gaitRows }
  }, [videos])

  const cards: Array<{ value: string; label: string; valueClass: string }> = [
    {
      value: String(stats.total),
      label: t('stats.totalVideos'),
      valueClass: 'text-geysirweiss',
    },
    {
      value: String(stats.doneCount),
      label: t('stats.doneVideos'),
      valueClass: 'text-geysirweiss',
    },
    {
      value: stats.topGait ?? '–',
      label: t('stats.topGait'),
      valueClass: stats.topGait
        ? isToelt(stats.topGait)
          ? 'text-nordlicht'
          : 'text-gletscherblau'
        : 'text-geysirweiss/40',
    },
    {
      value: String(stats.contributions),
      label: t('stats.contributions'),
      valueClass: 'text-geysirweiss',
    },
  ]

  if (stats.total === 0) return null

  return (
    <div className="w-full max-w-4xl mx-auto space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map(card => (
          <div key={card.label} className="bg-lava rounded-xl px-4 py-3">
            <div className={['text-2xl font-bold leading-tight', card.valueClass].join(' ')}>
              {card.value}
            </div>
            <div className="text-geysirweiss/40 text-xs mt-1">{card.label}</div>
          </div>
        ))}
      </div>

      {stats.gaitRows.length > 0 && (
        <div className="bg-lava rounded-xl px-4 py-3 space-y-2">
          {stats.gaitRows.map(row => (
            <div key={row.gait} className="flex items-center gap-3">
              <span className="text-geysirweiss/55 text-xs w-20 shrink-0 truncate">{row.gait}</span>
              <div className="flex-1 bg-lava/60 rounded-full h-1.5 overflow-hidden">
                <div
                  className={['h-full rounded-full transition-all', row.isToelt ? 'bg-nordlicht' : 'bg-gletscherblau/40'].join(' ')}
                  style={{ width: `${Math.round(row.pct * 100)}%` }}
                />
              </div>
              <span className="text-geysirweiss/35 text-xs w-6 text-right shrink-0">{row.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
