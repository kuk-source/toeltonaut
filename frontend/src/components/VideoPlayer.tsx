import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getFrameKeypoints } from '../api/client'
import type { KeypointEntry } from '../types'

interface VideoPlayerProps {
  jobId: string
  onTimeUpdate?: (currentFrame: number) => void
  seekToMs?: { ms: number; seq: number }
  fps?: number
  horseName?: string | null
  speedMs?: number | null
}

const ESTIMATED_FPS  = 25
const PREFETCH_AHEAD = 3   // Frames vorausladen
const CACHE_MAX      = 40  // Maximale Cache-Einträge

const FETLOCK_NAMES = new Set([
  'Nearfrontfetlock', 'Offfrontfetlock', 'Nearhindfetlock', 'Offhindfetlock',
  'Nearfrontfoot', 'Offfrontfoot', 'Nearhindfoot', 'Offhindfoot',
])

function kpColor(name: string) {
  return FETLOCK_NAMES.has(name) ? '#00C896' : '#A8D8EA'
}
function kpOutline(name: string) {
  return FETLOCK_NAMES.has(name) ? '#005540' : '#0a3860'
}

function getVideoRenderBounds(video: HTMLVideoElement) {
  const cw = video.clientWidth
  const ch = video.clientHeight
  const vw = video.videoWidth
  const vh = video.videoHeight
  if (!vw || !vh) return { x: 0, y: 0, w: cw, h: ch }
  const cr = cw / ch
  const vr = vw / vh
  let rw: number, rh: number
  if (vr > cr) { rw = cw; rh = cw / vr }
  else          { rh = ch; rw = ch * vr }
  return { x: (cw - rw) / 2, y: (ch - rh) / 2, w: rw, h: rh }
}

type SkeletonEdge = [string, string, string]

const SKELETON_EDGES: SkeletonEdge[] = [
  ['Nose',             'Eye',              'rgba(240,244,248,0.55)'],
  ['Wither',           'Midshoulder',      'rgba(168,216,234,0.65)'],
  ['Midshoulder',      'Shoulder',         'rgba(168,216,234,0.65)'],
  ['Shoulder',         'Elbow',            'rgba(168,216,234,0.65)'],
  ['Elbow',            'Girth',            'rgba(168,216,234,0.65)'],
  ['Wither',           'Hip',              'rgba(168,216,234,0.65)'],
  ['Hip',              'Ischium',          'rgba(168,216,234,0.65)'],
  ['Hip',              'Stifle',           'rgba(168,216,234,0.65)'],
  ['Shoulder',         'Nearknee',         'rgba(0,200,150,0.7)'],
  ['Nearknee',         'Nearfrontfetlock', 'rgba(0,200,150,0.7)'],
  ['Nearfrontfetlock', 'Nearfrontfoot',    'rgba(0,200,150,0.7)'],
  ['Shoulder',         'Offknee',          'rgba(0,180,200,0.7)'],
  ['Offknee',          'Offfrontfetlock',  'rgba(0,180,200,0.7)'],
  ['Offfrontfetlock',  'Offfrontfoot',     'rgba(0,180,200,0.7)'],
  ['Stifle',           'Nearhindhock',     'rgba(0,150,255,0.7)'],
  ['Nearhindhock',     'Nearhindfetlock',  'rgba(0,150,255,0.7)'],
  ['Nearhindfetlock',  'Nearhindfoot',     'rgba(0,150,255,0.7)'],
  ['Ischium',          'Offhindhock',      'rgba(120,100,210,0.7)'],
  ['Offhindhock',      'Offhindfetlock',   'rgba(120,100,210,0.7)'],
  ['Offhindfetlock',   'Offhindfoot',      'rgba(120,100,210,0.7)'],
]

function drawKeypoints(ctx: CanvasRenderingContext2D, video: HTMLVideoElement, kps: KeypointEntry[]) {
  if (!kps.length) return
  const b = getVideoRenderBounds(video)
  const R = 5
  const kpMap = new Map<string, { px: number; py: number }>()
  kps.forEach(kp => kpMap.set(kp.name, { px: b.x + kp.x * b.w, py: b.y + kp.y * b.h }))
  ctx.save()
  ctx.lineWidth = 2.5
  ctx.lineCap = 'round'
  SKELETON_EDGES.forEach(([nameA, nameB, color]) => {
    const a = kpMap.get(nameA)
    const b2 = kpMap.get(nameB)
    if (!a || !b2) return
    ctx.strokeStyle = color
    ctx.beginPath()
    ctx.moveTo(a.px, a.py)
    ctx.lineTo(b2.px, b2.py)
    ctx.stroke()
  })
  ctx.restore()
  kps.forEach(kp => {
    const px = b.x + kp.x * b.w
    const py = b.y + kp.y * b.h
    ctx.beginPath()
    ctx.arc(px, py, R + 2, 0, Math.PI * 2)
    ctx.fillStyle = kpOutline(kp.name)
    ctx.fill()
    ctx.beginPath()
    ctx.arc(px, py, R, 0, Math.PI * 2)
    ctx.fillStyle = kpColor(kp.name)
    ctx.fill()
  })
}

function drawGaitOverlay(
  ctx: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  gait: string | null,
  horseName: string | null | undefined,
  speedMs: number | null | undefined,
) {
  const b = getVideoRenderBounds(video)
  const lines: { text: string; color: string; bold: boolean }[] = []
  if (gait)            lines.push({ text: gait,                               color: '#00C896', bold: true })
  if (horseName)       lines.push({ text: horseName,                          color: '#F0F4F8', bold: false })
  if (speedMs != null) lines.push({ text: `${(speedMs * 3.6).toFixed(1)} km/h`, color: '#A8D8EA', bold: false })
  if (!lines.length) return
  const pad = 8, lineH = 18
  const bx = b.x + 10, by = b.y + 10
  const bh = pad * 2 + lines.length * lineH - 2
  ctx.font = '13px Inter, sans-serif'
  const bw = Math.max(...lines.map(l => {
    ctx.font = l.bold ? 'bold 14px Inter, sans-serif' : '13px Inter, sans-serif'
    return ctx.measureText(l.text).width
  })) + pad * 2
  ctx.fillStyle = 'rgba(0,0,0,0.60)'
  ctx.beginPath()
  if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 6)
  else               ctx.rect(bx, by, bw, bh)
  ctx.fill()
  lines.forEach((l, i) => {
    ctx.font = l.bold ? 'bold 14px Inter, sans-serif' : '13px Inter, sans-serif'
    ctx.fillStyle = l.color
    ctx.fillText(l.text, bx + pad, by + pad + (i + 1) * lineH - 3)
  })
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

type KpCacheEntry = { keypoints: KeypointEntry[]; gait: string | null }

export default function VideoPlayer({ jobId, onTimeUpdate, seekToMs, fps, horseName, speedMs }: VideoPlayerProps) {
  const { t } = useTranslation()
  const videoRef     = useRef<HTMLVideoElement>(null)
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Refs für rAF-Loop (kein React-State auf dem kritischen Pfad)
  const kpRef          = useRef<KeypointEntry[]>([])
  const gaitRef        = useRef<string | null>(null)
  const showKpRef      = useRef(false)
  const showGaitRef    = useRef(true)
  const horseNameRef   = useRef(horseName)
  const speedMsRef     = useRef(speedMs)
  const rvfcHandleRef  = useRef(0)
  const jobIdRef       = useRef(jobId)
  const fpsRef         = useRef(fps ?? ESTIMATED_FPS)

  // Vorlade-Cache: Frame-Nummer → Keypoints+Gait
  const kpCacheRef      = useRef<Map<number, KpCacheEntry>>(new Map())
  const fetchingFrames  = useRef<Set<number>>(new Set())

  const [playing,       setPlaying]       = useState(false)
  const [currentTime,   setCurrentTime]   = useState(0)
  const [duration,      setDuration]      = useState(0)
  const [showKeypoints, setShowKeypoints] = useState(false)
  const [showGaitLabel, setShowGaitLabel] = useState(true)
  const [isFullscreen,  setIsFullscreen]  = useState(false)
  const [editingFrame,  setEditingFrame]  = useState(false)
  const [frameInputVal, setFrameInputVal] = useState('')

  // Refs mit State/Props synchron halten
  useEffect(() => { horseNameRef.current = horseName }, [horseName])
  useEffect(() => { speedMsRef.current = speedMs }, [speedMs])
  useEffect(() => { jobIdRef.current = jobId; kpCacheRef.current.clear(); fetchingFrames.current.clear() }, [jobId])
  useEffect(() => { fpsRef.current = fps ?? ESTIMATED_FPS }, [fps])
  useEffect(() => { showKpRef.current = showKeypoints }, [showKeypoints])
  useEffect(() => { showGaitRef.current = showGaitLabel }, [showGaitLabel])

  // Fullscreen-Wechsel erkennen
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  const effectiveFps = fps ?? ESTIMATED_FPS
  const src = `/api/download/${jobId}`

  // Einen Frame in den Cache laden (dedup via fetchingFrames)
  const prefetchFrame = useCallback((frameNr: number, tMs: number) => {
    if (kpCacheRef.current.has(frameNr)) return
    if (fetchingFrames.current.has(frameNr)) return
    fetchingFrames.current.add(frameNr)
    getFrameKeypoints(jobIdRef.current, frameNr, tMs)
      .then(d => {
        const entry: KpCacheEntry = { keypoints: d.keypoints, gait: d.gait ?? null }
        kpCacheRef.current.set(frameNr, entry)
        // Cache-Größe begrenzen: älteste Einträge löschen
        if (kpCacheRef.current.size > CACHE_MAX) {
          const oldest = kpCacheRef.current.keys().next().value
          if (oldest !== undefined) kpCacheRef.current.delete(oldest)
        }
      })
      .catch(() => {})
      .finally(() => fetchingFrames.current.delete(frameNr))
  }, [])

  // rVFC-Loop: Canvas frame-synchron zeichnen (feuert exakt wenn Browser Frame an Compositor übergibt)
  useEffect(() => {
    let active = true
    const video = videoRef.current
    if (!video) return

    type RvfcMetadata = { mediaTime: number }

    const doRedraw = () => {
      const canvas = canvasRef.current
      if (!canvas) return
      if (canvas.width !== video.clientWidth || canvas.height !== video.clientHeight) {
        canvas.width  = video.clientWidth
        canvas.height = video.clientHeight
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      if (showKpRef.current)   drawKeypoints(ctx, video, kpRef.current)
      if (showGaitRef.current) drawGaitOverlay(ctx, video, gaitRef.current, horseNameRef.current, speedMsRef.current)
    }

    const onFrame = (_now: number, metadata: RvfcMetadata) => {
      if (!active) return
      if (showKpRef.current || showGaitRef.current) {
        const frameNr = Math.round(metadata.mediaTime * fpsRef.current)
        const tMs     = metadata.mediaTime * 1000
        const cached  = kpCacheRef.current.get(frameNr)
        if (cached) {
          kpRef.current   = cached.keypoints
          gaitRef.current = cached.gait
        }
        prefetchFrame(frameNr, tMs)
        for (let a = 1; a <= PREFETCH_AHEAD; a++) {
          prefetchFrame(frameNr + a, tMs + a * 1000 / fpsRef.current)
        }
      }
      doRedraw()
      rvfcHandleRef.current = (video as any).requestVideoFrameCallback(onFrame)
    }

    rvfcHandleRef.current = (video as any).requestVideoFrameCallback(onFrame)

    // Canvas-Größe bei Fenster-Resize aktualisieren (rVFC feuert nur bei neuen Frames)
    const resizeObserver = new ResizeObserver(doRedraw)
    resizeObserver.observe(video)

    return () => {
      active = false
      ;(video as any).cancelVideoFrameCallback(rvfcHandleRef.current)
      resizeObserver.disconnect()
    }
  }, [jobId, prefetchFrame])

  // Forced Redraw wenn Overlays ein-/ausgeschaltet werden (Video kann pausiert sein)
  useEffect(() => {
    const video  = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (showKeypoints) drawKeypoints(ctx, video, kpRef.current)
    if (showGaitLabel) drawGaitOverlay(ctx, video, gaitRef.current, horseNameRef.current, speedMsRef.current)
  }, [showKeypoints, showGaitLabel])

  // Video-Events für UI-State (Fortschrittsbalken, Zeitanzeige)
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onTimeupdate     = () => { setCurrentTime(v.currentTime); onTimeUpdate?.(Math.floor(v.currentTime * fpsRef.current)) }
    const onLoadedmetadata = () => { setDuration(v.duration); setCurrentTime(v.currentTime) }
    const onPlay           = () => setPlaying(true)
    const onPause          = () => setPlaying(false)
    const onEnded          = () => setPlaying(false)
    v.addEventListener('timeupdate',     onTimeupdate)
    v.addEventListener('loadedmetadata', onLoadedmetadata)
    v.addEventListener('play',           onPlay)
    v.addEventListener('pause',          onPause)
    v.addEventListener('ended',          onEnded)
    return () => {
      v.removeEventListener('timeupdate',     onTimeupdate)
      v.removeEventListener('loadedmetadata', onLoadedmetadata)
      v.removeEventListener('play',           onPlay)
      v.removeEventListener('pause',          onPause)
      v.removeEventListener('ended',          onEnded)
    }
  }, [onTimeUpdate])

  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) void v.play()
    else v.pause()
  }, [])

  const stepFrame = useCallback((direction: number) => {
    const v = videoRef.current
    if (!v) return
    v.pause()
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + direction / fpsRef.current))
  }, [])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.code === 'Space')           { e.preventDefault(); togglePlay() }
      else if (e.code === 'ArrowLeft')  { e.preventDefault(); stepFrame(-1) }
      else if (e.code === 'ArrowRight') { e.preventDefault(); stepFrame(1)  }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [togglePlay, stepFrame])

  useEffect(() => {
    if (!seekToMs) return
    const v = videoRef.current
    if (!v) return
    v.currentTime = seekToMs.ms / 1000
  }, [seekToMs])

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current
    if (!v || duration === 0) return
    const newTime = (parseFloat(e.target.value) / 100) * duration
    v.currentTime = newTime
    setCurrentTime(newTime)
    onTimeUpdate?.(Math.floor(newTime * effectiveFps))
  }

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen()
    } else {
      void document.exitFullscreen()
    }
  }, [])

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div ref={containerRef} className="rounded-xl overflow-hidden bg-vulkan border border-geysirweiss/10"
         style={isFullscreen ? { display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', borderRadius: 0 } : {}}>

      {/* Video + Canvas */}
      <div className="relative flex-1"
           style={{ background: '#1A1A2E', overflow: 'hidden', minHeight: 0,
                    ...(isFullscreen ? {} : { maxHeight: '900px' }) }}>
        <video
          ref={videoRef}
          src={src}
          className="w-full h-full block"
          style={{ objectFit: 'contain', background: '#1A1A2E',
                   ...(isFullscreen ? {} : { maxHeight: '900px' }) }}
          preload="metadata"
          onMouseDown={(e) => { if (e.detail === 2) return; togglePlay() }}
        />
        <canvas
          ref={canvasRef}
          style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
        />
      </div>

      {/* Steuerleiste */}
      <div
        className="flex flex-col gap-2 px-3 py-2.5"
        style={{ background: 'rgba(45,45,58,0.95)', backdropFilter: 'blur(8px)',
                 ...(isFullscreen ? { flexShrink: 0 } : {}) }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <input
            type="range" min={0} max={100} step={0.1} value={progress}
            onChange={handleSeek}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
            style={{ accentColor: '#00C896' }}
          />
        </div>

        <div className="flex items-center gap-3">
          <button onClick={() => stepFrame(-1)} title={t('videoPlayer.prevFrame')}
            className="text-geysirweiss/60 hover:text-gletscherblau transition-colors text-sm font-mono leading-none select-none">◀◀</button>

          <button onClick={togglePlay} title={playing ? t('videoPlayer.pause') : t('videoPlayer.play')}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-nordlicht/20 hover:bg-nordlicht/40 text-nordlicht transition-colors text-base leading-none select-none">
            {playing ? '⏸' : '▶'}
          </button>

          <button onClick={() => stepFrame(1)} title={t('videoPlayer.nextFrame')}
            className="text-geysirweiss/60 hover:text-gletscherblau transition-colors text-sm font-mono leading-none select-none">▶▶</button>

          <span className="text-geysirweiss/50 text-xs font-mono ml-1 tabular-nums">
            {formatTime(currentTime)}&nbsp;/&nbsp;{formatTime(duration)}
          </span>

          {editingFrame ? (
            <input type="number" value={frameInputVal}
              className="w-14 bg-vulkan text-geysirweiss text-xs font-mono text-center border border-gletscherblau/40 rounded px-1 py-0.5 outline-none"
              onChange={e => setFrameInputVal(e.target.value)}
              onBlur={() => {
                const f = parseInt(frameInputVal, 10)
                const v = videoRef.current
                if (!isNaN(f) && v) v.currentTime = Math.max(0, Math.min(v.duration || 0, f / effectiveFps))
                setEditingFrame(false)
              }}
              onKeyDown={e => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                if (e.key === 'Escape') setEditingFrame(false)
              }}
              autoFocus />
          ) : (
            <span
              className="text-geysirweiss/30 text-xs font-mono tabular-nums cursor-pointer hover:text-gletscherblau/70 transition-colors select-none"
              onClick={() => { setFrameInputVal(String(Math.floor(currentTime * effectiveFps))); setEditingFrame(true) }}
              title={t('videoPlayer.frameJumpHint')}>
              Fr.{Math.floor(currentTime * effectiveFps)}
            </span>
          )}

          <div className="flex-1" />

          <button onClick={() => setShowGaitLabel(v => !v)}
            title={showGaitLabel ? t('videoPlayer.gaitLabelHide') : t('videoPlayer.gaitLabelShow')}
            className={['text-xs px-2.5 py-1 rounded-lg border transition-colors select-none',
              showGaitLabel ? 'border-nordlicht/60 text-nordlicht bg-nordlicht/10'
                            : 'border-lava/80 text-geysirweiss/40 hover:border-gletscherblau/40 hover:text-geysirweiss/70'].join(' ')}>
            Gangart
          </button>

          <button onClick={() => setShowKeypoints(v => !v)}
            title={showKeypoints ? t('videoPlayer.keypointsHide') : t('videoPlayer.keypointsShow')}
            className={['text-xs px-2.5 py-1 rounded-lg border transition-colors select-none',
              showKeypoints ? 'border-nordlicht/60 text-nordlicht bg-nordlicht/10'
                            : 'border-lava/80 text-geysirweiss/40 hover:border-gletscherblau/40 hover:text-geysirweiss/70'].join(' ')}>
            Keypoints
          </button>

          <a href={src} download={`toeltonaut_${jobId.slice(0, 8)}.mp4`}
            title={t('videoPlayer.download')}
            className="text-geysirweiss/40 hover:text-gletscherblau transition-colors text-base leading-none">⬇</a>

          <button onClick={toggleFullscreen}
            title={isFullscreen ? t('videoPlayer.exitFullscreen') : t('videoPlayer.fullscreen')}
            className="text-geysirweiss/40 hover:text-gletscherblau transition-colors leading-none"
            style={{ fontSize: '15px' }}>
            {isFullscreen ? '✕' : '⛶'}
          </button>
        </div>
      </div>
    </div>
  )
}
