import { useState } from 'react'
import { useTranslation } from 'react-i18next'

const TIPS_CONFIG = [
  { icon: '📐', titleKey: 'recordingGuide.tips.sideView.title',  textKey: 'recordingGuide.tips.sideView.text' },
  { icon: '🎥', titleKey: 'recordingGuide.tips.steady.title',    textKey: 'recordingGuide.tips.steady.text' },
  { icon: '⏱️', titleKey: 'recordingGuide.tips.duration.title',  textKey: 'recordingGuide.tips.duration.text' },
  { icon: '☀️', titleKey: 'recordingGuide.tips.light.title',     textKey: 'recordingGuide.tips.light.text' },
]

export default function RecordingGuide() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <div className="w-full max-w-xl mx-auto">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-center gap-2 text-geysirweiss/30 hover:text-geysirweiss/55 text-xs py-2 transition-colors group"
      >
        <span className="border-b border-dashed border-geysirweiss/20 group-hover:border-geysirweiss/40 transition-colors">
          {t('recordingGuide.toggle')}
        </span>
        <span className="text-[10px] transition-transform duration-200" style={{ transform: open ? 'rotate(180deg)' : 'none' }}>
          ▼
        </span>
      </button>

      {open && (
        <div className="mt-2 bg-lava/60 rounded-xl border border-islandblau/20 px-4 py-4 space-y-3">
          {TIPS_CONFIG.map(tip => (
            <div key={tip.titleKey} className="flex gap-3">
              <span className="text-base leading-none mt-0.5 shrink-0">{tip.icon}</span>
              <div>
                <span className="text-geysirweiss/75 text-xs font-medium">{t(tip.titleKey)}: </span>
                <span className="text-geysirweiss/45 text-xs">{t(tip.textKey)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
