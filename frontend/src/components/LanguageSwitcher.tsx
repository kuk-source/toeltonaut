import { useTranslation } from 'react-i18next'

const LANGUAGES = [
  { code: 'de', label: 'DE' },
  { code: 'en', label: 'EN' },
] as const

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const current = i18n.language?.slice(0, 2) ?? 'de'

  return (
    <div className="flex items-center gap-0.5">
      {LANGUAGES.map(({ code, label }) => (
        <button
          key={code}
          onClick={() => void i18n.changeLanguage(code)}
          className={[
            'text-xs px-2 py-1 rounded-md transition-colors font-medium',
            current === code
              ? 'text-gletscherblau bg-islandblau/20'
              : 'text-geysirweiss/30 hover:text-geysirweiss/60 hover:bg-lava/60',
          ].join(' ')}
          aria-pressed={current === code}
          aria-label={`Switch language to ${label}`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
