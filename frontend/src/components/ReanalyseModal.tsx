import { useState, useEffect } from 'react'

type Mode = 'gait-only' | 'full'

interface Props {
  onClose: () => void
  onConfirm: (mode: Mode) => void
}

const MODES: {
  id: Mode
  title: string
  description: string
  duration: string
  durationColor: string
  detail: string
}[] = [
  {
    id: 'gait-only',
    title: 'Schnell',
    description: 'Gangart-Erkennung auf gespeicherten Keypoints neu berechnen.',
    duration: '~2 Sek.',
    durationColor: 'text-nordlicht bg-nordlicht/15',
    detail: 'Skelett-Overlay bleibt unverändert. Kein Re-Upload.',
  },
  {
    id: 'full',
    title: 'Vollständig',
    description: 'Video komplett neu verarbeiten: YOLOv8 + MMPose + Re-Encoding.',
    duration: 'Minuten',
    durationColor: 'text-gletscherblau bg-islandblau/30',
    detail: 'Skelett-Overlay wird aktualisiert. Dauert je nach Videolänge.',
  },
]

export default function ReanalyseModal({ onClose, onConfirm }: Props) {
  const [selected, setSelected] = useState<Mode>('gait-only')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-vulkan/75 backdrop-blur-sm
                 animate-[fadeIn_150ms_ease-out]"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reanalyse-title"
    >
      <div className="bg-lava rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <h2 id="reanalyse-title" className="text-geysirweiss font-semibold text-sm">
            Neu analysieren
          </h2>
          <button
            onClick={onClose}
            className="text-geysirweiss/40 hover:text-geysirweiss/80 transition-colors text-lg leading-none"
            aria-label="Schließen"
          >
            ×
          </button>
        </div>

        {/* Mode Cards */}
        <div className="p-4 space-y-3">
          {MODES.map((m) => {
            const isActive = selected === m.id
            return (
              <button
                key={m.id}
                onClick={() => setSelected(m.id)}
                className={[
                  'w-full text-left rounded-xl border px-4 py-3.5 transition-all',
                  isActive
                    ? 'border-gletscherblau bg-islandblau/20 shadow-[0_0_0_1px_#A8D8EA33]'
                    : 'border-white/10 hover:border-white/20 bg-vulkan/40',
                ].join(' ')}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`font-semibold text-sm ${isActive ? 'text-gletscherblau' : 'text-geysirweiss'}`}>
                    {m.title}
                  </span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${m.durationColor}`}>
                    {m.duration}
                  </span>
                </div>
                <p className="text-geysirweiss/70 text-xs leading-relaxed">{m.description}</p>
                <p className="text-geysirweiss/35 text-xs mt-1">{m.detail}</p>
              </button>
            )
          })}
        </div>

        {/* Footer */}
        <div className="flex gap-3 px-4 pb-4">
          <button
            onClick={() => onConfirm(selected)}
            className="flex-1 bg-nordlicht hover:bg-nordlicht/80 text-vulkan font-semibold py-2.5 rounded-lg text-sm transition-colors"
          >
            Analyse starten
          </button>
          <button
            onClick={onClose}
            className="flex-1 border border-white/10 text-geysirweiss/50 hover:text-geysirweiss/80 hover:border-white/20 py-2.5 rounded-lg text-sm transition-colors"
          >
            Abbrechen
          </button>
        </div>

      </div>
    </div>
  )
}
