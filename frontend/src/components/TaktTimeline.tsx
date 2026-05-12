import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getTaktTimeline, getToltScore } from '../api/client'
import type { TaktTimeline as TaktTimelineData, TaktFrame, ToltScoreData } from '../types'

interface Props {
  jobId: string
  currentFrame?: number
  onSeek?: (ms: number) => void
  onFpsDetected?: (fps: number) => void
}

const TRACK_KEYS = ['VL', 'VR', 'HL', 'HR'] as const
type TrackKey = (typeof TRACK_KEYS)[number]

const TRACK_COLORS: Record<TrackKey, string> = {
  VL: '#A8D8EA',
  VR: '#A8D8EA',
  HL: '#00C896',
  HR: '#00C896',
}

const CONTACT_THRESHOLD = 0.75

function toRanges(frames: number[]): [number, number][] {
  if (frames.length === 0) return []
  const sorted = [...frames].sort((a, b) => a - b)
  const ranges: [number, number][] = []
  let start = sorted[0], end = sorted[0]
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] <= end + 3) { end = sorted[i] }
    else { ranges.push([start, end]); start = sorted[i]; end = sorted[i] }
  }
  ranges.push([start, end])
  return ranges
}

function drawNonSideViewOverlay(
  ctx: CanvasRenderingContext2D,
  nonSVFrames: number[],
  totalFrames: number,
  trackWidth: number,
  cssHeight: number,
) {
  if (nonSVFrames.length === 0) return
  const ranges = toRanges(nonSVFrames)
  const scaleX = trackWidth / Math.max(1, totalFrames - 1)
  for (const [startF, endF] of ranges) {
    const x1 = LABEL_WIDTH + startF * scaleX
    const x2 = LABEL_WIDTH + (endF + 1) * scaleX
    const w = Math.max(2, x2 - x1)
    ctx.save()
    ctx.fillStyle = 'rgba(26,26,46,0.62)'
    ctx.fillRect(x1, 0, w, cssHeight)
    ctx.beginPath()
    ctx.rect(x1, 0, w, cssHeight)
    ctx.clip()
    ctx.strokeStyle = 'rgba(240,244,248,0.08)'
    ctx.lineWidth = 1
    for (let d = -cssHeight; d < w + cssHeight; d += 7) {
      ctx.beginPath()
      ctx.moveTo(x1 + d, 0)
      ctx.lineTo(x1 + d + cssHeight, cssHeight)
      ctx.stroke()
    }
    ctx.restore()
  }
}
const TRACK_HEIGHT = 48
const LABEL_WIDTH = 36
const PADDING_TOP = 4
const PADDING_BOTTOM = 4

function drawTrack(
  ctx: CanvasRenderingContext2D,
  frames: TaktFrame[],
  color: string,
  opacity: number,
  x: number,
  y: number,
  width: number,
  height: number,
  totalFrames: number,
) {
  if (frames.length === 0) return

  const innerH = height - PADDING_TOP - PADDING_BOTTOM
  const scaleX = width / Math.max(1, totalFrames - 1)
  const scaleY = innerH

  ctx.save()
  ctx.globalAlpha = opacity

  // Draw contact phase fills first
  ctx.fillStyle = color
  let inContact = false
  let contactStart = 0

  for (let i = 0; i < frames.length; i++) {
    const f = frames[i]
    const isContact = f.y_norm > CONTACT_THRESHOLD
    const fx = x + f.frame * scaleX

    if (isContact && !inContact) {
      inContact = true
      contactStart = fx
    } else if (!isContact && inContact) {
      inContact = false
      ctx.globalAlpha = opacity * 0.55
      ctx.fillRect(contactStart, y + PADDING_TOP, fx - contactStart, innerH)
      ctx.globalAlpha = opacity
    }
  }
  if (inContact) {
    const lastFx = x + frames[frames.length - 1].frame * scaleX
    ctx.globalAlpha = opacity * 0.55
    ctx.fillRect(contactStart, y + PADDING_TOP, lastFx - contactStart, innerH)
    ctx.globalAlpha = opacity
  }

  // Draw the y_norm line
  ctx.beginPath()
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'

  for (let i = 0; i < frames.length; i++) {
    const f = frames[i]
    const fx = x + f.frame * scaleX
    // Flip y: y_norm 0 = top of lane, 1 = bottom
    const fy = y + PADDING_TOP + f.y_norm * scaleY
    if (i === 0) ctx.moveTo(fx, fy)
    else ctx.lineTo(fx, fy)
  }
  ctx.stroke()

  // Emphasise contact segments with a thicker stroke
  ctx.lineWidth = 3
  ctx.strokeStyle = color
  inContact = false
  let segStart = { x: 0, y: 0 }

  for (let i = 0; i < frames.length; i++) {
    const f = frames[i]
    const isContact = f.y_norm > CONTACT_THRESHOLD
    const fx = x + f.frame * scaleX
    const fy = y + PADDING_TOP + f.y_norm * scaleY

    if (isContact && !inContact) {
      inContact = true
      segStart = { x: fx, y: fy }
    } else if (!isContact && inContact) {
      inContact = false
      ctx.beginPath()
      ctx.moveTo(segStart.x, segStart.y)
      // re-draw the contact segment
      for (let j = i - 1; j >= 0 && frames[j].y_norm > CONTACT_THRESHOLD; j--) {
        // walk back to find start – already captured via segStart, just draw forward
      }
      ctx.lineTo(fx, fy)
      ctx.stroke()
    }
  }

  ctx.restore()
}

export default function TaktTimeline({ jobId, currentFrame, onSeek, onFpsDetected }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<TaktTimelineData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toltData, setToltData] = useState<ToltScoreData | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getTaktTimeline(jobId)
      .then(d => {
        setData(d)
        if (d.fps > 0) onFpsDetected?.(d.fps)
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [jobId, onFpsDetected])

  useEffect(() => {
    setToltData(null)
    getToltScore(jobId)
      .then(setToltData)
      .catch((e: unknown) => {
        console.log('ToltScore nicht verfügbar (ignoriert):', e)
      })
  }, [jobId])

  useEffect(() => {
    if (!data || !canvasRef.current || !containerRef.current) return

    const canvas = canvasRef.current
    const container = containerRef.current
    const dpr = window.devicePixelRatio || 1
    const cssWidth = container.clientWidth
    const cssHeight = TRACK_KEYS.length * TRACK_HEIGHT

    canvas.width = cssWidth * dpr
    canvas.height = cssHeight * dpr
    canvas.style.width = `${cssWidth}px`
    canvas.style.height = `${cssHeight}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)

    // Background
    ctx.fillStyle = '#1A1A2E'
    ctx.fillRect(0, 0, cssWidth, cssHeight)

    const trackWidth = cssWidth - LABEL_WIDTH

    TRACK_KEYS.forEach((key, idx) => {
      const trackY = idx * TRACK_HEIGHT
      const color = TRACK_COLORS[key]
      const opacity = key === 'VR' || key === 'HR' ? 0.7 : 1.0

      // Lane separator
      if (idx > 0) {
        ctx.fillStyle = 'rgba(240,244,248,0.06)'
        ctx.fillRect(0, trackY, cssWidth, 1)
      }

      // Label background
      ctx.fillStyle = '#2D2D3A'
      ctx.fillRect(0, trackY, LABEL_WIDTH, TRACK_HEIGHT)

      // Label text
      ctx.fillStyle = color
      ctx.globalAlpha = opacity
      ctx.font = `600 11px Inter, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(key, LABEL_WIDTH / 2, trackY + TRACK_HEIGHT / 2)
      ctx.globalAlpha = 1

      // Track area background
      ctx.fillStyle = 'rgba(45,45,58,0.5)'
      ctx.fillRect(LABEL_WIDTH, trackY, trackWidth, TRACK_HEIGHT)

      const frames = data.tracks[key]
      drawTrack(ctx, frames, color, opacity, LABEL_WIDTH, trackY, trackWidth, TRACK_HEIGHT, data.total_frames)
    })

    // Non-side-view overlay (frames where horse ran toward/away from camera)
    drawNonSideViewOverlay(ctx, data.non_side_view_frames ?? [], data.total_frames, trackWidth, cssHeight)

    // Tölt-Fehler-Markierungen (Trabeinlagen, Pass-Einlagen) als farbige Balken oben
    if (toltData && toltData.errors.length > 0) {
      for (const err of toltData.errors) {
        const [startF, endF] = err.frame_range
        const x1 = LABEL_WIDTH + (startF / Math.max(1, data.total_frames - 1)) * trackWidth
        const x2 = LABEL_WIDTH + ((endF + 1) / Math.max(1, data.total_frames - 1)) * trackWidth
        const w = Math.max(2, x2 - x1)
        if (err.severity === 'schwer') {
          ctx.fillStyle = 'rgba(200,16,46,0.8)'
        } else if (err.severity === 'mittel') {
          ctx.fillStyle = 'rgba(255,165,0,0.7)'
        } else {
          ctx.fillStyle = 'rgba(255,220,0,0.5)'
        }
        ctx.fillRect(x1, 0, w, 4)
      }
    }

    // Frame axis tick marks (every ~5 seconds if fps known)
    if (data.fps > 0) {
      const tickInterval = Math.round(data.fps * 5)
      ctx.strokeStyle = 'rgba(240,244,248,0.12)'
      ctx.lineWidth = 1
      for (let f = tickInterval; f < data.total_frames; f += tickInterval) {
        const fx = LABEL_WIDTH + (f / Math.max(1, data.total_frames - 1)) * (trackWidth)
        ctx.beginPath()
        ctx.moveTo(fx, 0)
        ctx.lineTo(fx, TRACK_KEYS.length * TRACK_HEIGHT)
        ctx.stroke()

        const secs = Math.round(f / data.fps)
        ctx.fillStyle = 'rgba(240,244,248,0.25)'
        ctx.font = '10px Inter, system-ui, sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(`${secs}s`, fx, 2)
      }
    }
  }, [data, toltData])

  useEffect(() => {
    if (!data || !overlayRef.current || !containerRef.current) return
    const canvas = overlayRef.current
    const container = containerRef.current
    const dpr = window.devicePixelRatio || 1
    const cssWidth = container.clientWidth
    const cssHeight = TRACK_KEYS.length * TRACK_HEIGHT

    canvas.width = cssWidth * dpr
    canvas.height = cssHeight * dpr
    canvas.style.width = `${cssWidth}px`
    canvas.style.height = `${cssHeight}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, cssWidth * dpr, cssHeight * dpr)
    ctx.scale(dpr, dpr)

    if (currentFrame === undefined || data.total_frames <= 1) return

    const trackWidth = cssWidth - LABEL_WIDTH
    const fx = LABEL_WIDTH + (currentFrame / Math.max(1, data.total_frames - 1)) * trackWidth

    ctx.strokeStyle = '#C8102E'
    ctx.lineWidth = 1.5
    ctx.globalAlpha = 0.9
    ctx.beginPath()
    ctx.moveTo(fx, 0)
    ctx.lineTo(fx, cssHeight)
    ctx.stroke()
  }, [data, currentFrame])

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || !containerRef.current || !onSeek) return
    const rect = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const trackWidth = rect.width - LABEL_WIDTH
    if (x < LABEL_WIDTH || trackWidth <= 0) return

    // Klick in Fehlerbalken (obere 8px CSS) → zum Start-Frame des nächstliegenden Fehlers springen
    if (y <= 8 && toltData && toltData.errors.length > 0) {
      const frac = Math.max(0, Math.min(1, (x - LABEL_WIDTH) / trackWidth))
      const clickFrame = Math.round(frac * (data.total_frames - 1))
      let nearest = toltData.errors[0]
      let minDist = Math.abs(clickFrame - nearest.frame_range[0])
      for (const err of toltData.errors) {
        const dist = Math.abs(clickFrame - err.frame_range[0])
        if (dist < minDist) { minDist = dist; nearest = err }
      }
      const errMs = data.fps > 0 ? (nearest.frame_range[0] / data.fps) * 1000 : nearest.frame_range[0] * 40
      onSeek(errMs)
      return
    }

    const frac = Math.max(0, Math.min(1, (x - LABEL_WIDTH) / trackWidth))
    const frame = Math.round(frac * (data.total_frames - 1))
    const ms = data.fps > 0 ? (frame / data.fps) * 1000 : frame * 40
    onSeek(ms)
  }, [data, toltData, onSeek])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-20 text-geysirweiss/40 text-sm">
        {t('timeline.loading')}
      </div>
    )
  }

  if (error || !data || TRACK_KEYS.every((k) => data.tracks[k].length === 0)) {
    return (
      <div className="rounded-xl bg-lava border border-geysirweiss/10 p-4 text-center text-sm text-geysirweiss/50">
        {t('timeline.notAvailable')}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="text-xs font-semibold text-geysirweiss/50 uppercase tracking-wider">
        {t('timeline.title')}
      </div>
      <div
        ref={containerRef}
        className="w-full rounded-xl overflow-hidden border border-geysirweiss/10 relative"
        role="img"
        aria-label={t('timeline.ariaLabel')}
      >
        <canvas ref={canvasRef} className="block w-full" />
        <canvas
          ref={overlayRef}
          className="absolute inset-0 w-full"
          style={{ cursor: onSeek ? 'pointer' : 'default' }}
          onClick={handleCanvasClick}
        />
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-1">
        <span className="text-xs text-geysirweiss/40 shrink-0">
          {t('timeline.toeltPattern')}&nbsp;
          <span className="font-mono text-geysirweiss/60">HL → VL → HR → VR</span>
        </span>
        <div className="flex items-center gap-3 ml-auto">
          {TRACK_KEYS.map((key) => (
            <div key={key} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{
                  backgroundColor: TRACK_COLORS[key],
                  opacity: key === 'VR' || key === 'HR' ? 0.7 : 1,
                }}
              />
              <span className="text-xs text-geysirweiss/60">{key}</span>
            </div>
          ))}
          <div className="flex items-center gap-1.5 ml-1">
            <span className="inline-block w-5 h-2.5 rounded-sm bg-gletscherblau/40" />
            <span className="text-xs text-geysirweiss/40">{t('timeline.groundContact')}</span>
          </div>
          {(data?.non_side_view_frames?.length ?? 0) > 0 && (
            <div className="flex items-center gap-1.5 ml-1">
              <span className="inline-block w-5 h-2.5 rounded-sm bg-vulkan/80 border border-geysirweiss/15" style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(240,244,248,0.12) 2px, rgba(240,244,248,0.12) 3px)' }} />
              <span className="text-xs text-geysirweiss/35">{t('timeline.notEvaluable')}</span>
            </div>
          )}
          {(toltData?.errors.length ?? 0) > 0 && (
            <div className="flex items-center gap-1.5 ml-1">
              <span className="inline-block w-5 h-1 rounded-sm" style={{ backgroundColor: 'rgba(200,16,46,0.8)' }} />
              <span className="text-xs text-geysirweiss/50">{t('timeline.errors')}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
