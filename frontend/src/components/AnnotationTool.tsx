import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getFrameKeypoints, getFrameUrl, saveAnnotation } from '../api/client'
import type { KeypointEntry } from '../types'

interface Props {
  jobId: string
  onClose: () => void
}

// Horse-10 / MMPose – 22 Keypoints (einziges aktives Schema)
const KEYPOINT_COLORS: Record<string, string> = {
  Nose: '#F0F4F8', Eye: '#F0F4F8', Poll: '#F0F4F8',
  Wither: '#A8D8EA', Shoulder: '#A8D8EA', Midshoulder: '#A8D8EA',
  Elbow: '#A8D8EA', Girth: '#A8D8EA', Hip: '#A8D8EA', Stifle: '#A8D8EA', Ischium: '#A8D8EA',
  Nearknee: '#A8D8EA', Nearfrontfetlock: '#00C896', Nearfrontfoot: '#00C896',
  Offknee: '#A8D8EA', Offfrontfetlock: '#00C896', Offfrontfoot: '#00C896',
  Nearhindhock: '#A8D8EA', Nearhindfetlock: '#00C896', Nearhindfoot: '#00C896',
  Offhindhock: '#A8D8EA', Offhindfetlock: '#00C896', Offhindfoot: '#00C896',
}

const DEFAULT_COLOR = '#A8D8EA'
const RADIUS_NORMAL = 3
const RADIUS_ACTIVE = 5

// Muss: MVP-Minimal-Set laut CLAUDE.md (Fesselgelenke ×4 + Sprunggelenke ×2 + Karpus ×2)
const KP_MUSS = new Set([
  'Nearfrontfetlock', 'Offfrontfetlock', 'Nearhindfetlock', 'Offhindfetlock',
  'Nearhindhock', 'Offhindhock',
  'Nearknee', 'Offknee',
])

const KP_LABELS: Record<string, string> = {
  Nose: 'Nase', Eye: 'Auge', Poll: 'Genick',
  Wither: 'Widerrist', Shoulder: 'Schulter', Midshoulder: 'Schulter Mitte',
  Elbow: 'Ellbogen', Girth: 'Gurt', Hip: 'Hüfte', Stifle: 'Kniegelenk HB', Ischium: 'Sitzbeinhöcker',
  Nearknee: 'Karpus L', Nearfrontfetlock: 'Fesselg. VL ★', Nearfrontfoot: 'Huf VL',
  Offknee: 'Karpus R', Offfrontfetlock: 'Fesselg. VR ★', Offfrontfoot: 'Huf VR',
  Nearhindhock: 'Sprunggelenk L', Nearhindfetlock: 'Fesselg. HL ★', Nearhindfoot: 'Huf HL',
  Offhindhock: 'Sprunggelenk R', Offhindfetlock: 'Fesselg. HR ★', Offhindfoot: 'Huf HR',
}

const FRAME_STEP = 30   // = VID_STRIDE(2) × 15 → landet immer auf gespeicherten Frames

type SkeletonEdge = [string, string, string]

const SKELETON_EDGES: SkeletonEdge[] = [
  ['Nose',             'Eye',              'rgba(240,244,248,0.45)'],
  ['Wither',           'Midshoulder',      'rgba(168,216,234,0.55)'],
  ['Midshoulder',      'Shoulder',         'rgba(168,216,234,0.55)'],
  ['Shoulder',         'Elbow',            'rgba(168,216,234,0.55)'],
  ['Elbow',            'Girth',            'rgba(168,216,234,0.55)'],
  ['Wither',           'Hip',              'rgba(168,216,234,0.55)'],
  ['Hip',              'Ischium',          'rgba(168,216,234,0.55)'],
  ['Hip',              'Stifle',           'rgba(168,216,234,0.55)'],
  ['Shoulder',         'Nearknee',         'rgba(0,200,150,0.6)'],
  ['Nearknee',         'Nearfrontfetlock', 'rgba(0,200,150,0.6)'],
  ['Nearfrontfetlock', 'Nearfrontfoot',    'rgba(0,200,150,0.6)'],
  ['Shoulder',         'Offknee',          'rgba(0,180,200,0.6)'],
  ['Offknee',          'Offfrontfetlock',  'rgba(0,180,200,0.6)'],
  ['Offfrontfetlock',  'Offfrontfoot',     'rgba(0,180,200,0.6)'],
  ['Stifle',           'Nearhindhock',     'rgba(0,150,255,0.6)'],
  ['Nearhindhock',     'Nearhindfetlock',  'rgba(0,150,255,0.6)'],
  ['Nearhindfetlock',  'Nearhindfoot',     'rgba(0,150,255,0.6)'],
  ['Ischium',          'Offhindhock',      'rgba(120,100,210,0.6)'],
  ['Offhindhock',      'Offhindfetlock',   'rgba(120,100,210,0.6)'],
  ['Offhindfetlock',   'Offhindfoot',      'rgba(120,100,210,0.6)'],
]

// ── Einführungs-Screen ───────────────────────────────────────────────────────

function AnnotationIntro({ onStart }: { onStart: () => void }) {
  const { t } = useTranslation()
  const steps = [
    t('annotation.steps.step1'),
    t('annotation.steps.step2'),
    t('annotation.steps.step3'),
    t('annotation.steps.step4'),
  ]
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div
        className="bg-vulkan rounded-2xl w-full max-w-xl shadow-2xl border border-geysirweiss/10 overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="annotation-intro-title"
      >
        <div className="px-6 pt-6 pb-4 space-y-5">
          <div>
            <h2 id="annotation-intro-title" className="text-geysirweiss font-semibold text-lg">{t('annotation.title')}</h2>
            <p className="text-geysirweiss/45 text-sm mt-1">
              {t('annotation.introDescription')}
            </p>
          </div>

          {/* Beispielbild */}
          <div className="bg-lava rounded-xl border border-islandblau/20 px-4 py-5">
            <p className="text-geysirweiss/50 text-xs mb-3 text-center">{t('annotation.introExampleCaption')}</p>
            <HorseKeypointSVG />
            <div className="flex items-center justify-center gap-4 mt-3 text-[10px]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-nordlicht inline-block" />{t('annotation.legendFetlock')}</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gletscherblau inline-block" />Weitere Gelenke</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-geysirweiss/50 inline-block" />Kopf &amp; Rumpf</span>
            </div>
          </div>

          {/* Schritte */}
          <ol className="space-y-2 text-sm text-geysirweiss/60">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="shrink-0 w-5 h-5 rounded-full bg-islandblau/40 text-gletscherblau text-xs flex items-center justify-center font-semibold">
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="px-6 pb-5 flex gap-3">
          <button
            onClick={onStart}
            className="flex-1 py-2.5 rounded-xl bg-islandblau text-geysirweiss font-medium text-sm hover:bg-islandblau/80 transition-colors"
          >
            {t('annotation.introStart')}
          </button>
        </div>
      </div>
    </div>
  )
}

function HorseKeypointSVG() {
  return (
    <img
      src="/horse_keypoints.png"
      alt="Töltender Islandpferd mit Keypoints"
      style={{ width: '100%', display: 'block' }}
    />
  )
}

// ── Konfidenz-Farbe ─────────────────────────────────────────────────────────

function keypointColor(conf: number, isManual: boolean): string {
  if (isManual) return '#A8D8EA'   // Gletscherblau – manuell gesetzt
  if (conf >= 0.65) return '#00C896' // Nordlicht-Grün – sicher
  if (conf >= 0.30) return '#F5A623' // Orange – mittlere Sicherheit
  return '#C8102E'                   // Flaggenrot – unsicher
}

// ── Symmetrie-Paare ─────────────────────────────────────────────────────────

const SYMMETRY_PAIRS: [string, string][] = [
  ['Nearfrontfetlock', 'Offfrontfetlock'],
  ['Nearfrontfoot',    'Offfrontfoot'],
  ['Nearknee',         'Offknee'],
  ['Nearhindfetlock',  'Offhindfetlock'],
  ['Nearhindfoot',     'Offhindfoot'],
  ['Nearhindhock',     'Offhindhock'],
]
const SYMMETRY_MAP = new Map<string, string>()
SYMMETRY_PAIRS.forEach(([l, r]) => { SYMMETRY_MAP.set(l, r); SYMMETRY_MAP.set(r, l) })

// ── Haupt-Komponente ─────────────────────────────────────────────────────────

const INTRO_KEY = 'annotation-intro-seen'

export default function AnnotationTool({ jobId, onClose }: Props) {
  const { t } = useTranslation()
  const [showIntro, setShowIntro] = useState(() => !localStorage.getItem(INTRO_KEY))
  const [frameNr, setFrameNr] = useState(0)
  const [frameNrInput, setFrameNrInput] = useState('0')
  const [keypoints, setKeypoints] = useState<KeypointEntry[]>([])
  const [originalKeypoints, setOriginalKeypoints] = useState<KeypointEntry[]>([])
  const [activeKpIndex, setActiveKpIndex] = useState<number | null>(null)
  const [hoverKpIndex, setHoverKpIndex] = useState<number | null>(null)
  const [ghostKeypoints, setGhostKeypoints] = useState<KeypointEntry[]>([])
  const [showGhost, setShowGhost] = useState(true)
  const [symmetryLock, setSymmetryLock] = useState(false)
  const isFirstFrameLoad = useRef(true)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [savedFlash, setSavedFlash] = useState(false)
  const [copyMsg, setCopyMsg] = useState<string | null>(null)
  const [imgNaturalSize, setImgNaturalSize] = useState<{ w: number; h: number } | null>(null)
  const [imgDisplaySize, setImgDisplaySize] = useState<{ w: number; h: number } | null>(null)
  const [imgError, setImgError] = useState(false)
  const [imgLoading, setImgLoading] = useState(true)

  const [zoom, setZoom] = useState(1)
  const [pan,  setPan]  = useState({ x: 0, y: 0 })
  const [armedKpName, setArmedKpName] = useState<string | null>(null)

  // Active-Learning: verfolge den unsichersten gesehenen Frame
  const [lowestConfFrame, setLowestConfFrame] = useState<{ nr: number; avg: number } | null>(null)

  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const imgRef       = useRef<HTMLImageElement>(null)
  const viewportRef  = useRef<HTMLDivElement>(null)
  const wrapperRef   = useRef<HTMLDivElement>(null)
  const draggingRef  = useRef<number | null>(null)
  const isPanning    = useRef(false)
  const panStart     = useRef({ mx: 0, my: 0, px: 0, py: 0 })

  // Undo/Redo
  const undoStackRef   = useRef<KeypointEntry[][]>([])
  const redoStackRef   = useRef<KeypointEntry[][]>([])
  const dragStartRef   = useRef<KeypointEntry[] | null>(null)

  const pushUndo = useCallback((snapshot: KeypointEntry[]) => {
    undoStackRef.current.push(snapshot)
    if (undoStackRef.current.length > 50) undoStackRef.current.shift()
    redoStackRef.current = []
  }, [])

  // Konvertiert Screen-Koordinaten → Canvas-Koordinaten (zoom-bereinigt)
  const screenToCanvas = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return { mx: 0, my: 0 }
    const rect = canvas.getBoundingClientRect()
    const inv = canvas.offsetWidth / rect.width   // = 1/zoom
    return { mx: (clientX - rect.left) * inv, my: (clientY - rect.top) * inv }
  }

  const frameUrl = getFrameUrl(jobId, frameNr)

  const loadKeypoints = useCallback(async (nr: number) => {
    // Vor dem Laden neuer Keypoints: aktuelle als Ghost speichern (nicht beim ersten Frame)
    if (!isFirstFrameLoad.current) {
      setKeypoints(prev => { setGhostKeypoints(prev); return prev })
    }
    isFirstFrameLoad.current = false
    try {
      const data = await getFrameKeypoints(jobId, nr)
      setKeypoints(data.keypoints)
      setOriginalKeypoints(data.keypoints)

      // Active-Learning: durchschnittliche Konfidenz berechnen, unsichersten Frame merken
      const real = data.keypoints.filter(kp => kp.confidence < 2.0)
      if (real.length > 0) {
        const avg = real.reduce((sum, kp) => sum + kp.confidence, 0) / real.length
        setLowestConfFrame(prev => (!prev || avg < prev.avg) ? { nr, avg } : prev)
      }
    } catch {
      setKeypoints([])
      setOriginalKeypoints([])
    }
  }, [jobId])

  useEffect(() => {
    void loadKeypoints(frameNr)
    setImgError(false)
    setImgLoading(true)
  }, [frameNr, loadKeypoints])

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img || !imgNaturalSize || !imgDisplaySize) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scaleX = imgDisplaySize.w / imgNaturalSize.w
    const scaleY = imgDisplaySize.h / imgNaturalSize.h
    canvas.width = imgDisplaySize.w
    canvas.height = imgDisplaySize.h
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Ghost-Rendering: vorheriges Frame als semi-transparente Überlagerung
    if (showGhost && ghostKeypoints.length > 0) {
      const ghostKpMap = new Map<string, { cx: number; cy: number }>()
      ghostKeypoints.forEach(kp => ghostKpMap.set(kp.name, {
        cx: kp.x * imgNaturalSize.w * scaleX,
        cy: kp.y * imgNaturalSize.h * scaleY,
      }))
      ctx.save()
      ctx.globalAlpha = 0.18
      ctx.lineWidth = 1.5
      ctx.lineCap = 'round'
      SKELETON_EDGES.forEach(([nameA, nameB]) => {
        const a = ghostKpMap.get(nameA)
        const b = ghostKpMap.get(nameB)
        if (!a || !b) return
        ctx.strokeStyle = '#A8D8EA'
        ctx.beginPath()
        ctx.moveTo(a.cx, a.cy)
        ctx.lineTo(b.cx, b.cy)
        ctx.stroke()
      })
      ghostKeypoints.forEach(kp => {
        const pos = ghostKpMap.get(kp.name)
        if (!pos) return
        ctx.fillStyle = '#A8D8EA'
        ctx.beginPath()
        ctx.arc(pos.cx, pos.cy, 3, 0, Math.PI * 2)
        ctx.fill()
      })
      ctx.restore()
    }

    // Skelett-Linien (unter den Dots)
    const kpMap = new Map<string, { cx: number; cy: number; conf: number; isManual: boolean }>()
    keypoints.forEach(kp => kpMap.set(kp.name, {
      cx: kp.x * imgNaturalSize.w * scaleX,
      cy: kp.y * imgNaturalSize.h * scaleY,
      conf: kp.confidence,
      isManual: kp.confidence >= 2.0,
    }))
    ctx.save()
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    SKELETON_EDGES.forEach(([nameA, nameB]) => {
      const a = kpMap.get(nameA)
      const b = kpMap.get(nameB)
      if (!a || !b) return
      // Linienfarbe: Keypoint mit niedrigerer Konfidenz bestimmt die Farbe
      const lowerConf = Math.min(a.conf, b.conf)
      const eitherManual = a.isManual && b.isManual
      ctx.strokeStyle = keypointColor(lowerConf, eitherManual) + '99' // 60% Opazität
      ctx.beginPath()
      ctx.moveTo(a.cx, a.cy)
      ctx.lineTo(b.cx, b.cy)
      ctx.stroke()
    })
    ctx.restore()

    keypoints.forEach((kp, i) => {
      const cx = kp.x * imgNaturalSize.w * scaleX
      const cy = kp.y * imgNaturalSize.h * scaleY
      const isActive = i === activeKpIndex
      const isHover = i === hoverKpIndex
      const r = isActive || isHover ? RADIUS_ACTIVE : RADIUS_NORMAL
      const isManual    = kp.confidence >= 2.0
      const isOccluded  = kp.confidence === 0.0
      const isLowConf   = !isManual && !isOccluded && kp.confidence < 0.3
      const color = keypointColor(kp.confidence, isManual)

      ctx.shadowColor = 'rgba(0,0,0,0.7)'
      ctx.shadowBlur = 5

      // Okkludiert: gestrichelter oranger Ring
      if (isOccluded) {
        ctx.save()
        ctx.setLineDash([3, 3])
        ctx.beginPath()
        ctx.arc(cx, cy, RADIUS_NORMAL + 3, 0, Math.PI * 2)
        ctx.strokeStyle = 'rgba(255,165,0,0.7)'
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.setLineDash([])
        ctx.restore()
      }

      // Niedrige Konfidenz: gestrichelter roter Ring außen
      if (isLowConf && !isActive) {
        ctx.save()
        ctx.setLineDash([3, 3])
        ctx.beginPath()
        ctx.arc(cx, cy, r + 3, 0, Math.PI * 2)
        ctx.strokeStyle = 'rgba(200,16,46,0.75)'
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.setLineDash([])
        ctx.restore()
      }

      if (isActive) {
        ctx.beginPath()
        ctx.arc(cx, cy, r + 4, 0, Math.PI * 2)
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2.5
        ctx.stroke()
      }

      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = isLowConf ? 0.70 : 1.0
      ctx.fill()
      ctx.globalAlpha = 1.0

      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.strokeStyle = isManual ? '#FFD700' : 'rgba(0,0,0,0.4)'
      ctx.lineWidth = isManual ? 2.5 : 1
      ctx.stroke()

      ctx.shadowBlur = 0

      // Label direkt am Punkt wenn aktiv
      if (isActive) {
        const label = KP_LABELS[kp.name] ?? kp.name
        ctx.font = 'bold 11px Inter, sans-serif'
        const tw = ctx.measureText(label).width
        const lx = cx + r + 6
        const ly = cy + 4
        ctx.fillStyle = 'rgba(0,0,0,0.65)'
        ctx.fillRect(lx - 2, ly - 12, tw + 6, 16)
        ctx.fillStyle = '#ffffff'
        ctx.fillText(label, lx + 1, ly)
      }
    })
  }, [keypoints, activeKpIndex, hoverKpIndex, imgNaturalSize, imgDisplaySize, ghostKeypoints, showGhost])

  useEffect(() => { drawCanvas() }, [drawCanvas])

  const applySymmetry = useCallback((movedKpName: string, movedX: number, movedY: number) => {
    const mirrorName = SYMMETRY_MAP.get(movedKpName)
    if (!mirrorName) return
    const mirroredX = 1.0 - movedX
    const mirrorKp: KeypointEntry = { name: mirrorName, x: mirroredX, y: movedY, confidence: 2.0 }
    setKeypoints(prev => {
      const existing = prev.findIndex(k => k.name === mirrorName)
      if (existing >= 0) {
        return prev.map((k, i) => i === existing ? mirrorKp : k)
      } else {
        return [...prev, mirrorKp]
      }
    })
  }, [])

  const getCanvasKpIndex = (clientX: number, clientY: number): number => {
    if (!imgNaturalSize || !imgDisplaySize) return -1
    const { mx, my } = screenToCanvas(clientX, clientY)
    const scaleX = imgDisplaySize.w / imgNaturalSize.w
    const scaleY = imgDisplaySize.h / imgNaturalSize.h
    for (let i = keypoints.length - 1; i >= 0; i--) {
      const cx = keypoints[i].x * imgNaturalSize.w * scaleX
      const cy = keypoints[i].y * imgNaturalSize.h * scaleY
      if (Math.sqrt((mx - cx) ** 2 + (my - cy) ** 2) <= RADIUS_ACTIVE + 6) return i
    }
    return -1
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    // Bewaffneter Modus: Klick platziert den Keypoint
    if (armedKpName && imgNaturalSize && imgDisplaySize) {
      const { mx, my } = screenToCanvas(e.clientX, e.clientY)
      const scaleX = imgDisplaySize.w / imgNaturalSize.w
      const scaleY = imgDisplaySize.h / imgNaturalSize.h
      const newKp: KeypointEntry = {
        name: armedKpName,
        x: Math.max(0, Math.min(1, mx / (imgNaturalSize.w * scaleX))),
        y: Math.max(0, Math.min(1, my / (imgNaturalSize.h * scaleY))),
        confidence: 2.0,
      }
      // Snapshot vor Placement
      pushUndo([...keypoints])
      // Bestehenden Punkt gleichen Namens ersetzen (kein Duplikat)
      setKeypoints(prev => [...prev.filter(k => k.name !== armedKpName), newKp])
      if (symmetryLock) applySymmetry(newKp.name, newKp.x, newKp.y)
      setArmedKpName(null)
      return
    }
    const idx = getCanvasKpIndex(e.clientX, e.clientY)
    if (idx >= 0) {
      dragStartRef.current = [...keypoints]
      draggingRef.current = idx
      setActiveKpIndex(idx)
    } else {
      // Kein Keypoint getroffen → pannen
      isPanning.current = true
      panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y }
      if (canvasRef.current) canvasRef.current.style.cursor = 'grabbing'
    }
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas || !imgNaturalSize || !imgDisplaySize) return

    if (isPanning.current) {
      setPan({
        x: panStart.current.px + e.clientX - panStart.current.mx,
        y: panStart.current.py + e.clientY - panStart.current.my,
      })
      return
    }

    const { mx, my } = screenToCanvas(e.clientX, e.clientY)
    const scaleX = imgDisplaySize.w / imgNaturalSize.w
    const scaleY = imgDisplaySize.h / imgNaturalSize.h

    if (draggingRef.current !== null) {
      const idx = draggingRef.current
      const newX = Math.max(0, Math.min(1, mx / (imgNaturalSize.w * scaleX)))
      const newY = Math.max(0, Math.min(1, my / (imgNaturalSize.h * scaleY)))
      setKeypoints(prev =>
        prev.map((kp, i) => i === idx ? { ...kp, x: newX, y: newY, confidence: 2.0 } : kp)
      )
    } else {
      const hoverIdx = getCanvasKpIndex(e.clientX, e.clientY)
      setHoverKpIndex(hoverIdx >= 0 ? hoverIdx : null)
      canvas.style.cursor = armedKpName ? 'crosshair' : (hoverIdx >= 0 ? 'grab' : 'move')
    }
  }

  const handleMouseUp = () => {
    if (draggingRef.current !== null && dragStartRef.current !== null) {
      pushUndo(dragStartRef.current)
      if (symmetryLock) {
        const draggedKp = keypoints[draggingRef.current]
        if (draggedKp) applySymmetry(draggedKp.name, draggedKp.x, draggedKp.y)
      }
    }
    dragStartRef.current = null
    draggingRef.current = null
    isPanning.current = false
    if (canvasRef.current) canvasRef.current.style.cursor = 'move'
  }

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
    const newZoom = Math.min(8, Math.max(0.2, zoom * factor))
    const vp = viewportRef.current
    if (!vp) return
    const rect = vp.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const imgX = (mx - pan.x) / zoom
    const imgY = (my - pan.y) / zoom
    setPan({ x: mx - imgX * newZoom, y: my - imgY * newZoom })
    setZoom(newZoom)
  }

  const resetZoom = () => {
    const vp = viewportRef.current
    const img = imgRef.current
    if (!vp || !img) return
    const vpW = vp.clientWidth
    const vpH = vp.clientHeight
    const fitZoom = Math.min(vpW / img.offsetWidth, vpH / img.offsetHeight, 1)
    setZoom(fitZoom)
    setPan({ x: (vpW - img.offsetWidth * fitZoom) / 2, y: (vpH - img.offsetHeight * fitZoom) / 2 })
  }

  const handleImgLoad = () => {
    const img = imgRef.current
    if (!img) return
    setImgNaturalSize({ w: img.naturalWidth, h: img.naturalHeight })
    setImgDisplaySize({ w: img.offsetWidth, h: img.offsetHeight })
    setImgError(false)
    setImgLoading(false)
    // Zoom zurücksetzen sobald neues Bild geladen
    const vp = viewportRef.current
    if (!vp) return
    const vpW = vp.clientWidth
    const vpH = vp.clientHeight
    const fitZoom = Math.min(vpW / img.offsetWidth, vpH / img.offsetHeight, 1)
    setZoom(fitZoom)
    setPan({ x: (vpW - img.offsetWidth * fitZoom) / 2, y: (vpH - img.offsetHeight * fitZoom) / 2 })
  }

  const goToFrame = useCallback((nr: number) => {
    const hasUnsaved = JSON.stringify(keypoints) !== JSON.stringify(originalKeypoints)
    if (hasUnsaved && !window.confirm(t('annotation.discardConfirm'))) return
    const n = Math.max(0, nr)
    setFrameNr(n)
    setFrameNrInput(String(n))
    setActiveKpIndex(null)
    setArmedKpName(null)
  }, [keypoints, originalKeypoints, t])

  const handleUndo = useCallback(() => {
    const prev = undoStackRef.current.pop()
    if (!prev) return
    redoStackRef.current.push([...keypoints])
    setKeypoints(prev)
    setActiveKpIndex(null)
  }, [keypoints])

  const handleRedo = useCallback(() => {
    const next = redoStackRef.current.pop()
    if (!next) return
    undoStackRef.current.push([...keypoints])
    setKeypoints(next)
    setActiveKpIndex(null)
  }, [keypoints])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName ?? '').toUpperCase()
      const inputFocused = tag === 'INPUT' || tag === 'TEXTAREA'

      if (e.key === 'Escape') { setArmedKpName(null); return }

      // Undo / Redo
      if (e.ctrlKey && !e.shiftKey && e.key === 'z') { e.preventDefault(); handleUndo(); return }
      if (e.ctrlKey && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) { e.preventDefault(); handleRedo(); return }

      // Delete aktiven Keypoint
      if ((e.key === 'Delete' || e.key === 'Backspace') && activeKpIndex !== null) {
        e.preventDefault()
        pushUndo([...keypoints])
        setKeypoints(prev => prev.filter((_, j) => j !== activeKpIndex))
        setActiveKpIndex(null)
        return
      }

      // Tab → nächster unsicherer Keypoint
      if (e.key === 'Tab') {
        e.preventDefault()
        const lowConf = keypoints
          .map((kp, i) => ({ kp, i }))
          .filter(({ kp }) => kp.confidence < 0.5 && kp.confidence < 2.0)
          .sort((a, b) => a.kp.confidence - b.kp.confidence)
        if (!lowConf.length) return
        const currentPos = lowConf.findIndex(({ i }) => i === activeKpIndex)
        const next = lowConf[(currentPos + 1) % lowConf.length]
        setActiveKpIndex(next.i)
        return
      }

      // Frame-Navigation – nur wenn kein Input-Feld fokussiert
      if (!inputFocused) {
        if (e.key === 'a' || e.key === 'ArrowLeft') {
          e.preventDefault()
          if (e.shiftKey) goToFrame(frameNr - FRAME_STEP)
          else goToFrame(frameNr - 1)
          return
        }
        if (e.key === 'd' || e.key === 'ArrowRight') {
          e.preventDefault()
          if (e.shiftKey) goToFrame(frameNr + FRAME_STEP)
          else goToFrame(frameNr + 1)
          return
        }
        if (e.key === 'g' || e.key === 'G') {
          e.preventDefault()
          setShowGhost(v => !v)
          return
        }
        if (e.key === 's' || e.key === 'S') {
          e.preventDefault()
          setSymmetryLock(v => !v)
          return
        }
        // C – Keypoints vom Vorgänger-Frame kopieren
        if (e.key === 'c' || e.key === 'C') {
          e.preventDefault()
          void (async () => {
            if (frameNr <= 0) return
            try {
              const data = await getFrameKeypoints(jobId, frameNr - 1)
              if (!data.keypoints || data.keypoints.length === 0) return
              const copied = data.keypoints.map(kp => ({ ...kp, confidence: 0.7 }))
              pushUndo([...keypoints])
              setKeypoints(copied)
              setCopyMsg(`Keypoints von Frame ${frameNr - 1} kopiert`)
              setTimeout(() => setCopyMsg(null), 1500)
            } catch {
              // stilles Fail – kein Frame vorhanden
            }
          })()
          return
        }
        // Q – Aktiven Keypoint als okkludiert markieren / zurücksetzen
        if (e.key === 'q' || e.key === 'Q') {
          e.preventDefault()
          if (activeKpIndex === null) return
          pushUndo([...keypoints])
          setKeypoints(prev =>
            prev.map((kp, i) => {
              if (i !== activeKpIndex) return kp
              return { ...kp, confidence: kp.confidence === 0.0 ? 0.5 : 0.0 }
            })
          )
          return
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeKpIndex, handleUndo, handleRedo, pushUndo, keypoints, frameNr, jobId, goToFrame])

  const handleSave = async () => {
    setSaving(true)
    setSaveMsg(null)
    try {
      await saveAnnotation(jobId, frameNr, keypoints)
      setOriginalKeypoints(keypoints)
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2000)
    } catch {
      setSaveMsg(t('annotation.saveError'))
      setTimeout(() => setSaveMsg(null), 3000)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    pushUndo([...keypoints])
    setKeypoints(originalKeypoints)
    setActiveKpIndex(null)
  }

  const hasChanges = JSON.stringify(keypoints) !== JSON.stringify(originalKeypoints)

  const handleClose = () => {
    if (hasChanges && !window.confirm(t('annotation.discardConfirm'))) return
    onClose()
  }

  const activeKp = activeKpIndex !== null ? keypoints[activeKpIndex] : null

  if (showIntro) {
    return <AnnotationIntro onStart={() => {
      localStorage.setItem(INTRO_KEY, '1')
      setShowIntro(false)
    }} />
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div
        className="bg-vulkan rounded-2xl w-full max-w-6xl max-h-[95vh] flex flex-col overflow-hidden shadow-2xl border border-geysirweiss/10"
        role="dialog"
        aria-modal="true"
        aria-labelledby="annotation-tool-title"
      >

        {/* Kopfzeile */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-geysirweiss/10 shrink-0">
          <div className="flex items-center gap-4">
            <div>
              <h2 id="annotation-tool-title" className="text-geysirweiss font-semibold text-base">{t('annotation.title')}</h2>
              <p className="text-geysirweiss/35 text-xs font-mono">{jobId.slice(0, 8)}</p>
            </div>
            {/* Anleitung inline */}
            <div className="hidden sm:flex items-center gap-1.5 bg-islandblau/20 rounded-lg px-3 py-1.5 text-xs text-gletscherblau/80">
              <span>①</span><span>{t('annotation.headerInstruction1')}</span>
              <span className="text-gletscherblau/40 mx-1">·</span>
              <span>②</span><span>{t('annotation.headerInstruction2')}</span>
              <span className="text-gletscherblau/40 mx-1">·</span>
              <span>③</span><span>{t('annotation.headerInstruction3')}</span>
            </div>
            {/* Zoom-Steuerung */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setZoom(z => Math.min(8, z * 1.25))}
                className="w-7 h-7 flex items-center justify-center rounded-lg bg-geysirweiss/10 hover:bg-geysirweiss/20 text-geysirweiss/60 hover:text-geysirweiss text-sm transition-colors"
                title={t('annotation.zoomIn')}
                aria-label={t('annotation.zoomIn')}
              >+</button>
              <button
                onClick={resetZoom}
                className="px-2 h-7 flex items-center justify-center rounded-lg bg-geysirweiss/10 hover:bg-geysirweiss/20 text-geysirweiss/60 hover:text-geysirweiss text-xs font-mono transition-colors min-w-[3rem]"
                title={t('annotation.zoomReset')}
                aria-label={t('annotation.zoomReset')}
              >{Math.round(zoom * 100)}%</button>
              <button
                onClick={() => setZoom(z => Math.max(0.2, z / 1.25))}
                className="w-7 h-7 flex items-center justify-center rounded-lg bg-geysirweiss/10 hover:bg-geysirweiss/20 text-geysirweiss/60 hover:text-geysirweiss text-sm transition-colors"
                title={t('annotation.zoomOut')}
                aria-label={t('annotation.zoomOut')}
              >−</button>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowIntro(true)}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-geysirweiss/10 hover:bg-geysirweiss/20 text-geysirweiss/50 hover:text-geysirweiss transition-colors text-sm font-semibold"
              title={t('annotation.showHelp')}
              aria-label={t('annotation.showHelp')}
            >?</button>
            <button
              onClick={handleClose}
              className="text-geysirweiss/50 hover:text-geysirweiss transition-colors text-xl leading-none w-8 h-8 flex items-center justify-center rounded-lg hover:bg-geysirweiss/10"
              aria-label={t('annotation.close')}
            >×</button>
          </div>
        </div>

        {/* Hauptbereich */}
        <div className="flex flex-1 overflow-hidden min-h-0">

          {/* Canvas */}
          <div
            ref={viewportRef}
            className="flex-1 bg-black/40 relative overflow-hidden min-w-0"
            onWheel={handleWheel}
          >
            {/* Bewaffneter-Modus-Banner */}
            {armedKpName && (
              <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 bg-islandblau/90 border border-gletscherblau/60 rounded-xl px-4 py-2 text-sm text-gletscherblau shadow-lg pointer-events-none">
                ＋ {KP_LABELS[armedKpName] ?? armedKpName} — Klick ins Bild zum Platzieren · Esc abbr.
              </div>
            )}

            {imgLoading && !imgError && (
              <div className="absolute inset-0 flex items-center justify-center text-geysirweiss/30 text-sm pointer-events-none z-10">
                {t('annotation.frameLoading', { frame: frameNr })}
              </div>
            )}

            {imgError ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center space-y-2 p-8">
                  <p className="text-geysirweiss/40 text-sm">
                    {t('annotation.frameLoadError', { frame: frameNr })}
                  </p>
                  <p className="text-geysirweiss/25 text-xs">
                    {t('annotation.frameLoadHint')}
                  </p>
                </div>
              </div>
            ) : (
              <div
                ref={wrapperRef}
                style={{
                  position: 'absolute',
                  transformOrigin: '0 0',
                  transform: `translate(${pan.x}px,${pan.y}px) scale(${zoom})`,
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  ref={imgRef}
                  src={frameUrl}
                  alt={`Frame ${frameNr}`}
                  className="block select-none"
                  onLoad={handleImgLoad}
                  onError={() => { setImgError(true); setImgLoading(false) }}
                  draggable={false}
                />
                {imgDisplaySize && (
                  <canvas
                    ref={canvasRef}
                    className="absolute inset-0 pointer-events-auto"
                    style={{ width: imgDisplaySize.w, height: imgDisplaySize.h }}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={() => {
                      handleMouseUp()
                      setHoverKpIndex(null)
                    }}
                  />
                )}
              </div>
            )}

            {/* Copy-Toast */}
            {copyMsg && (
              <div className="absolute top-2 right-3 z-20 bg-islandblau/90 border border-gletscherblau/60 rounded-xl px-4 py-2 text-sm text-gletscherblau shadow-lg pointer-events-none">
                {copyMsg}
              </div>
            )}

            {/* Hinweis wenn Punkt aktiv */}
            {activeKp && (
              <div className="absolute bottom-3 left-1/2 -translate-x-1/2 bg-lava/90 rounded-lg px-3 py-1.5 text-xs text-gletscherblau pointer-events-none whitespace-nowrap z-10">
                {t('annotation.dragHint', { name: KP_LABELS[activeKp.name] ?? activeKp.name })}
              </div>
            )}

            {/* Hinweis wenn keine Keypoints */}
            {!imgLoading && !imgError && imgDisplaySize && keypoints.length === 0 && (
              <div className="absolute inset-x-0 bottom-3 flex justify-center pointer-events-none z-10">
                <div className="bg-lava/90 rounded-lg px-4 py-2 text-xs text-geysirweiss/50 text-center max-w-xs">
                  {t('annotation.noKeypointsMsg', { frame: frameNr })}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="w-68 shrink-0 flex flex-col border-l border-geysirweiss/10 bg-lava overflow-hidden" style={{ width: 272 }}>

            {/* Frame-Navigation */}
            <div className="p-4 border-b border-geysirweiss/10 space-y-3">
              <div className="text-geysirweiss/50 text-xs font-medium uppercase tracking-wider">
                {t('annotation.frameLabel')}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => goToFrame(frameNr - FRAME_STEP)}
                  disabled={frameNr === 0}
                  className="px-3 py-1.5 rounded-lg bg-vulkan text-geysirweiss/70 hover:text-geysirweiss hover:bg-geysirweiss/10 disabled:opacity-30 disabled:cursor-not-allowed text-sm transition-colors"
                  title={`–${FRAME_STEP} Frames`}
                  aria-label={`${FRAME_STEP} Frames zurück`}
                >
                  ←
                </button>
                <input
                  type="number"
                  min={0}
                  value={frameNrInput}
                  onChange={e => setFrameNrInput(e.target.value)}
                  onBlur={() => {
                    const nr = parseInt(frameNrInput, 10)
                    if (!isNaN(nr) && nr >= 0) goToFrame(nr)
                    else setFrameNrInput(String(frameNr))
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const nr = parseInt(frameNrInput, 10)
                      if (!isNaN(nr) && nr >= 0) goToFrame(nr)
                    }
                  }}
                  className="flex-1 bg-vulkan text-geysirweiss text-sm rounded-lg px-3 py-1.5 border border-geysirweiss/20 focus:outline-none focus:border-gletscherblau text-center"
                />
                <button
                  onClick={() => goToFrame(frameNr + FRAME_STEP)}
                  className="px-3 py-1.5 rounded-lg bg-vulkan text-geysirweiss/70 hover:text-geysirweiss hover:bg-geysirweiss/10 text-sm transition-colors"
                  title={`+${FRAME_STEP} Frames`}
                  aria-label={`${FRAME_STEP} Frames vor`}
                >
                  →
                </button>
              </div>
              <div className="text-geysirweiss/25 text-xs text-center">{t('annotation.frameStep', { step: FRAME_STEP })}</div>
            </div>

            {/* Keypoint-Liste mit Muss/Soll-Gruppen (platziert + unplatziert) */}
            <div className="flex-1 overflow-y-auto p-3">
              {(() => {
                const placedNames = new Set(keypoints.map(kp => kp.name))
                // Alle 22 bekannten Keypoints – nicht nur die von der KI erkannten
                const allKpNames = Object.keys(KP_LABELS)
                const unplacedNames = allKpNames.filter(name => !placedNames.has(name))

                const allMussPlaced  = keypoints.filter(kp => KP_MUSS.has(kp.name))
                const allSollPlaced  = keypoints.filter(kp => !KP_MUSS.has(kp.name))
                const unplacedMuss   = unplacedNames.filter(name => KP_MUSS.has(name))
                const unplacedSoll   = unplacedNames.filter(name => !KP_MUSS.has(name))

                const renderPlaced = (kp: KeypointEntry) => {
                  const i = keypoints.indexOf(kp)
                  const isManual  = kp.confidence >= 2.0
                  const isLowConf = !isManual && kp.confidence < 0.5
                  const isActive  = i === activeKpIndex
                  const color = KEYPOINT_COLORS[kp.name] ?? DEFAULT_COLOR
                  const isMuss = KP_MUSS.has(kp.name)
                  const deleteKp = (e: React.MouseEvent) => {
                    e.stopPropagation()
                    setKeypoints(prev => prev.filter((_, j) => j !== i))
                    if (activeKpIndex === i) setActiveKpIndex(null)
                  }
                  return (
                    <div key={kp.name} className="flex items-center gap-0.5">
                      <button
                        onClick={() => setActiveKpIndex(i === activeKpIndex ? null : i)}
                        className={[
                          'flex-1 flex items-center gap-2 px-2 py-1 rounded-lg text-left transition-colors text-xs',
                          isActive
                            ? 'bg-islandblau/40 border border-gletscherblau/50'
                            : isLowConf
                            ? 'hover:bg-flaggenrot/5 border border-flaggenrot/20'
                            : 'hover:bg-geysirweiss/5 border border-transparent',
                        ].join(' ')}
                      >
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color, opacity: isLowConf ? 0.5 : 1 }} />
                        <span className={`flex-1 truncate ${isMuss ? 'text-geysirweiss/90' : isLowConf ? 'text-geysirweiss/40' : 'text-geysirweiss/55'}`}>
                          {KP_LABELS[kp.name] ?? kp.name}
                        </span>
                        {isManual && <span className="text-[#FFD700] text-[10px] shrink-0" title="Manuell korrigiert">★</span>}
                        {isLowConf && (
                          <span className="text-flaggenrot/70 text-[10px] shrink-0 font-mono" title={`Konfidenz: ${Math.round(kp.confidence * 100)}%`}>
                            {Math.round(kp.confidence * 100)}%
                          </span>
                        )}
                      </button>
                      <button
                        onClick={deleteKp}
                        title={`${KP_LABELS[kp.name] ?? kp.name} entfernen (Del)`}
                        className="shrink-0 w-5 h-5 flex items-center justify-center rounded text-flaggenrot/30 hover:text-flaggenrot hover:bg-flaggenrot/10 transition-colors text-[11px]"
                      >×</button>
                    </div>
                  )
                }

                const renderUnplaced = (name: string) => {
                  const isArmed = armedKpName === name
                  const color = KEYPOINT_COLORS[name] ?? DEFAULT_COLOR
                  return (
                    <button
                      key={name}
                      onClick={() => setArmedKpName(isArmed ? null : name)}
                      title={isArmed ? 'Escape zum Abbrechen' : 'Klicken → ins Bild klicken zum Platzieren'}
                      className={[
                        'w-full flex items-center gap-2 px-2 py-1 rounded-lg text-left transition-all text-xs border',
                        isArmed
                          ? 'border-gletscherblau/70 bg-islandblau/30 text-gletscherblau animate-pulse'
                          : 'border-dashed border-geysirweiss/15 text-geysirweiss/30 hover:border-geysirweiss/35 hover:text-geysirweiss/50',
                      ].join(' ')}
                    >
                      <span className="w-2 h-2 rounded-full shrink-0 border border-current opacity-50" style={{ borderColor: color }} />
                      <span className="flex-1 truncate">{KP_LABELS[name] ?? name}</span>
                      <span className="text-[10px] shrink-0">{isArmed ? '✕ Esc' : '+'}</span>
                    </button>
                  )
                }

                return (
                  <>
                    <div className="mb-2">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-nordlicht/70 px-1 mb-1">
                        {t('annotation.groupMuss')} · {allMussPlaced.length}/{allMussPlaced.length + unplacedMuss.length}
                      </div>
                      <div className="space-y-0.5">
                        {allMussPlaced.map(renderPlaced)}
                        {unplacedMuss.map(renderUnplaced)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-geysirweiss/35 px-1 mb-1 mt-1">
                        {t('annotation.groupSoll')} · {allSollPlaced.length}/{allSollPlaced.length + unplacedSoll.length}
                      </div>
                      <div className="space-y-0.5">
                        {allSollPlaced.map(renderPlaced)}
                        {unplacedSoll.map(renderUnplaced)}
                      </div>
                    </div>
                  </>
                )
              })()}
            </div>

            {/* Legende */}
            <div className="px-4 py-2 border-t border-geysirweiss/10 space-y-1">
              {/* Konfidenz-Farbkodierung */}
              <div className="text-[9px] font-semibold uppercase tracking-wider text-geysirweiss/25 mb-1">Konfidenz</div>
              <div className="flex items-center gap-1.5 text-[10px] text-geysirweiss/50">
                <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ backgroundColor: '#00C896' }} />
                <span>conf ≥ 0.65 – sicher</span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-geysirweiss/50">
                <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ backgroundColor: '#F5A623' }} />
                <span>conf 0.30–0.64 – prüfen</span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-geysirweiss/50">
                <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ backgroundColor: '#C8102E' }} />
                <span>conf &lt; 0.30 – unsicher</span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-geysirweiss/50">
                <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ backgroundColor: '#A8D8EA' }} />
                <span>manuell gesetzt</span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-geysirweiss/50">
                <span className="w-2 h-2 rounded-full inline-block shrink-0 border border-dashed" style={{ borderColor: 'rgba(255,165,0,0.7)', backgroundColor: 'transparent' }} />
                <span>okkludiert (Q)</span>
              </div>
              <div className="mt-2 pt-2 border-t border-geysirweiss/10 space-y-1">
                <div className="text-[9px] font-semibold uppercase tracking-wider text-geysirweiss/25 mb-1">Tastatur</div>
                {[
                  ['A / D', '±1 Frame'],
                  ['⇧+A / ⇧+D', `±${FRAME_STEP} Frames`],
                  ['Tab', 'Nächster unsicherer KP'],
                  ['Ctrl+Z / Y', 'Rückgängig / Wdh.'],
                  ['Del', 'KP entfernen'],
                  ['G', 'Ghost ein/aus'],
                  ['S', 'Symmetrie an/aus'],
                  ['C', 'KPs vom Vorgänger kopieren'],
                  ['Q', 'Okkludiert togglen'],
                  ['Esc', 'Abbrechen'],
                ].map(([key, desc]) => (
                  <div key={key} className="flex items-center justify-between text-[9px] text-geysirweiss/25">
                    <span className="font-mono bg-geysirweiss/5 px-1 rounded">{key}</span>
                    <span>{desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Aktionen */}
            <div className="p-4 border-t border-geysirweiss/10 space-y-2 shrink-0">
              {/* Active-Learning: Unsichersten Frame anspringen */}
              {lowestConfFrame !== null && lowestConfFrame.nr !== frameNr && (
                <button
                  onClick={() => goToFrame(lowestConfFrame.nr)}
                  title={`Frame ${lowestConfFrame.nr} – Ø ${Math.round(lowestConfFrame.avg * 100)}% Konfidenz`}
                  className="w-full py-1.5 rounded-xl border border-flaggenrot/40 text-flaggenrot/80 hover:border-flaggenrot hover:text-flaggenrot hover:bg-flaggenrot/10 text-xs transition-colors flex items-center justify-center gap-1.5"
                >
                  <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ backgroundColor: '#C8102E' }} />
                  Unsichersten Frame — #{lowestConfFrame.nr} (Ø {Math.round(lowestConfFrame.avg * 100)}%)
                </button>
              )}
              {/* Ghost + Symmetrie Toggles */}
              <div className="flex gap-2">
                <button
                  onClick={() => setShowGhost(v => !v)}
                  title="Ghost-Overlay ein/aus (G)"
                  className={[
                    'flex-1 py-1.5 rounded-xl border text-xs transition-colors',
                    showGhost
                      ? 'border-gletscherblau/50 text-gletscherblau bg-islandblau/20'
                      : 'border-geysirweiss/20 text-geysirweiss/40 hover:border-geysirweiss/40',
                  ].join(' ')}
                >
                  Ghost {showGhost ? 'AN' : 'AUS'}
                </button>
                <button
                  onClick={() => setSymmetryLock(v => !v)}
                  title="Symmetrie: linke/rechte Seite spiegeln (S)"
                  className={[
                    'flex-1 py-1.5 rounded-xl border text-xs transition-colors',
                    symmetryLock
                      ? 'border-islandblau/60 text-gletscherblau bg-islandblau/20'
                      : 'border-geysirweiss/20 text-geysirweiss/40 hover:border-geysirweiss/40',
                  ].join(' ')}
                >
                  &#8644; Symm. {symmetryLock ? 'AN' : 'AUS'}
                </button>
              </div>
              <button
                onClick={() => void handleSave()}
                disabled={saving || keypoints.length === 0}
                className={[
                  'w-full py-2.5 rounded-xl text-sm font-medium transition-all',
                  savedFlash
                    ? 'bg-nordlicht/60 text-vulkan'
                    : keypoints.length > 0 && !saving
                    ? 'bg-nordlicht text-vulkan hover:bg-nordlicht/90'
                    : 'bg-geysirweiss/10 text-geysirweiss/40',
                  saving || keypoints.length === 0 ? 'opacity-50 cursor-not-allowed' : '',
                ].join(' ')}
              >
                {saving ? t('annotation.saving') : savedFlash ? t('annotation.saveSaved') : t('annotation.save')}
              </button>
              {saveMsg && (
                <div className="text-xs text-center px-3 py-1.5 rounded-lg bg-flaggenrot/20 text-flaggenrot">
                  {saveMsg}
                </div>
              )}
              <button
                onClick={handleReset}
                disabled={!hasChanges}
                className="w-full py-2 rounded-xl border border-geysirweiss/20 text-geysirweiss/50 hover:border-gletscherblau hover:text-gletscherblau disabled:opacity-25 disabled:cursor-not-allowed text-sm transition-colors"
              >
                {t('annotation.reset')}
              </button>
              <button
                onClick={() => {
                  if (keypoints.length === 0) return
                  if (window.confirm(t('annotation.clearAllConfirm'))) {
                    pushUndo([...keypoints])
                    setKeypoints([])
                    setActiveKpIndex(null)
                  }
                }}
                disabled={keypoints.length === 0}
                className="w-full py-2 rounded-xl border border-flaggenrot/25 text-flaggenrot/50 hover:border-flaggenrot/60 hover:text-flaggenrot/80 disabled:opacity-25 disabled:cursor-not-allowed text-sm transition-colors"
              >
                {t('annotation.clearAll')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
