import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { getVideos, deleteJob, getDownloadUrl, getExportUrl, getCocoZipUrl, resetAnnotations, reanalyseJob } from '../api/client'
import type { VideoEntry } from '../types'
import StatsDashboard from './StatsDashboard'
import AnnotationTool from './AnnotationTool'
import MetadataEditModal from './MetadataEditModal'

const POLL_INTERVAL = 30_000

// Status labels are now translated at render time via useTranslation
const STATUS_LABEL_KEY: Record<VideoEntry['status'], string> = {
  queued:     'library.statusQueued',
  processing: 'library.statusProcessing',
  done:       'library.statusDone',
  error:      'library.statusError',
  expired:    'library.statusExpired',
}

const STATUS_COLOR: Record<VideoEntry['status'], string> = {
  queued:     'text-geysirweiss/50 bg-lava/60',
  processing: 'text-gletscherblau bg-islandblau/30',
  done:       'text-nordlicht bg-nordlicht/15',
  error:      'text-flaggenrot bg-flaggenrot/15',
  expired:    'text-geysirweiss/30 bg-lava/40',
}

const GAIT_OPTIONS = ['Alle', 'Tölt', 'Trab', 'Schritt', 'Galopp', 'Rennpass', 'Gemischt'] as const
type GaitFilter = typeof GAIT_OPTIONS[number]

const STATUS_OPTIONS = ['Alle', 'Fertig', 'Läuft', 'Fehler'] as const
type StatusFilter = typeof STATUS_OPTIONS[number]

const SORT_OPTIONS = [
  { value: 'newest', labelKey: 'library.sortNewest' },
  { value: 'oldest', labelKey: 'library.sortOldest' },
  { value: 'name',   labelKey: 'library.sortName' },
] as const
type SortOption = typeof SORT_OPTIONS[number]['value']

const STATUS_MAP: Record<StatusFilter, VideoEntry['status'] | null> = {
  Alle:   null,
  Fertig: 'done',
  Läuft:  'processing',
  Fehler: 'error',
}

const STATUS_OPTION_LABEL_KEY: Record<StatusFilter, string> = {
  Alle:   'library.filterAll',
  Fertig: 'library.filterDone',
  Läuft:  'library.filterRunning',
  Fehler: 'library.filterError',
}

const GAIT_OPTION_LABEL_KEY: Record<GaitFilter, string | null> = {
  Alle:     'library.filterAll',
  Tölt:     null,
  Trab:     null,
  Schritt:  null,
  Galopp:   null,
  Rennpass: null,
  Gemischt: null,
}

function gaitMatchesFilter(entry: VideoEntry, filter: GaitFilter): boolean {
  if (filter === 'Alle') return true
  // "Gemischt" ist ein Nutzer-Label, nicht vom KI erkannt → immer gait_label prüfen
  if (filter === 'Gemischt') return (entry.gait_label ?? '').toLowerCase() === 'gemischt'
  const gait = (entry.gait_detected ?? entry.gait_label ?? '').toLowerCase()
  return gait.startsWith(filter.toLowerCase()) || (
    filter === 'Tölt' && (gait === 'toelt' || gait === 'tölt')
  )
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

const CHIP_ACTIVE   = 'bg-islandblau text-geysirweiss'
const CHIP_INACTIVE = 'border border-lava/60 text-geysirweiss/50 hover:border-gletscherblau/40 hover:text-geysirweiss/70'
const CHIP_BASE     = 'text-xs px-3 py-1 rounded-full font-medium transition-colors cursor-pointer select-none'

interface Props {
  onSelect?: (entry: VideoEntry) => void
}

export default function VideoLibrary({ onSelect }: Props) {
  const { t } = useTranslation()
  const [videos, setVideos]           = useState<VideoEntry[]>([])
  const [loading, setLoading]         = useState(true)
  const [deletingId, setDeletingId]   = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deleteErrorId, setDeleteErrorId]     = useState<string | null>(null)
  const [annotatingId, setAnnotatingId]       = useState<string | null>(null)
  const [editingId, setEditingId]             = useState<string | null>(null)
  const [confirmResetId, setConfirmResetId]   = useState<string | null>(null)
  const [resettingId, setResettingId]         = useState<string | null>(null)
  const [resetErrorId, setResetErrorId]       = useState<string | null>(null)
  const [reanalysingId, setReanalysingId]     = useState<string | null>(null)
  const [reanalyseOkId, setReanalyseOkId]     = useState<string | null>(null)

  const [gaitFilter,   setGaitFilter]   = useState<GaitFilter>('Alle')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('Alle')
  const [visibleCount, setVisibleCount] = useState(12)
  const [sortBy,       setSortBy]       = useState<SortOption>('newest')
  const [search,       setSearch]       = useState('')

  const fetchVideos = useCallback(async () => {
    try {
      const data = await getVideos()
      setVideos(data)
    } catch {
      // stale data bleibt sichtbar
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchVideos()
    const id = setInterval(() => void fetchVideos(), POLL_INTERVAL)
    return () => clearInterval(id)
  }, [fetchVideos])

  const handleDelete = async (jobId: string) => {
    setConfirmDeleteId(null)
    setDeleteErrorId(null)
    setDeletingId(jobId)
    try {
      await deleteJob(jobId)
      setVideos(v => v.filter(e => e.job_id !== jobId))
    } catch {
      setDeleteErrorId(jobId)
    } finally {
      setDeletingId(null)
    }
  }

  const handleMetadataSave = (jobId: string, updated: Partial<VideoEntry>) => {
    setVideos(v => v.map(e => e.job_id === jobId ? { ...e, ...updated } : e))
  }

  const handleResetAnnotations = async (jobId: string) => {
    setConfirmResetId(null)
    setResetErrorId(null)
    setResettingId(jobId)
    try {
      await resetAnnotations(jobId)
      setVideos(v => v.map(e => e.job_id === jobId ? { ...e, is_annotated: false } : e))
    } catch {
      setResetErrorId(jobId)
    } finally {
      setResettingId(null)
    }
  }

  const handleReanalyse = async (jobId: string) => {
    setReanalysingId(jobId)
    try {
      await reanalyseJob(jobId)
      setReanalyseOkId(jobId)
      setTimeout(() => { setReanalyseOkId(null); void fetchVideos() }, 3000)
    } catch { /* Fehler still ignorieren – Button wird einfach wieder aktiv */ }
    finally { setReanalysingId(null) }
  }

  const filtered = useMemo(() => {
    setVisibleCount(12)
    let list = videos.slice()

    if (gaitFilter !== 'Alle') {
      list = list.filter(e => gaitMatchesFilter(e, gaitFilter))
    }

    const statusTarget = STATUS_MAP[statusFilter]
    if (statusTarget !== null) {
      list = list.filter(e => e.status === statusTarget)
    }

    if (search.trim() !== '') {
      const q = search.trim().toLowerCase()
      list = list.filter(e =>
        e.filename.toLowerCase().includes(q) ||
        (e.horse_name ?? '').toLowerCase().includes(q)
      )
    }

    list.sort((a, b) => {
      if (sortBy === 'newest') return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      if (sortBy === 'oldest') return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      const nameA = (a.horse_name ?? a.filename).toLowerCase()
      const nameB = (b.horse_name ?? b.filename).toLowerCase()
      return nameA.localeCompare(nameB, 'de')
    })

    return list
  }, [videos, gaitFilter, statusFilter, sortBy, search])

  const filtersActive =
    gaitFilter !== 'Alle' || statusFilter !== 'Alle' || search.trim() !== ''

  if (loading) {
    return (
      <div className="w-full max-w-4xl mx-auto mt-2">
        <div className="text-geysirweiss/30 text-sm text-center py-8">{t('library.loading')}</div>
      </div>
    )
  }

  return (
    <>
    <section className="w-full max-w-4xl mx-auto mt-2">
      <h3 className="text-geysirweiss/60 text-xs uppercase tracking-widest font-semibold mb-4 px-1">
        {t('library.title')}
      </h3>

      {videos.length > 0 && <StatsDashboard videos={videos} />}

      {/* Filter-Leiste */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4 mt-5 px-1">
        {/* Gangart-Filter */}
        <div className="flex flex-wrap gap-1.5">
          {GAIT_OPTIONS.map(g => (
            <button
              key={g}
              onClick={() => setGaitFilter(g)}
              className={[CHIP_BASE, gaitFilter === g ? CHIP_ACTIVE : CHIP_INACTIVE].join(' ')}
            >
              {GAIT_OPTION_LABEL_KEY[g] ? t(GAIT_OPTION_LABEL_KEY[g]!) : g}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-lava/60 hidden sm:block" />

        {/* Status-Filter */}
        <div className="flex flex-wrap gap-1.5">
          {STATUS_OPTIONS.map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={[CHIP_BASE, statusFilter === s ? CHIP_ACTIVE : CHIP_INACTIVE].join(' ')}
            >
              {t(STATUS_OPTION_LABEL_KEY[s])}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-lava/60 hidden sm:block" />

        {/* Sortierung */}
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value as SortOption)}
          className="text-xs bg-lava border border-lava/60 text-geysirweiss/70 rounded-lg px-2 py-1 focus:outline-none focus:border-gletscherblau/40 cursor-pointer"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{t(o.labelKey)}</option>
          ))}
        </select>

        {/* Such-Input */}
        <div className="relative">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t('library.searchPlaceholder')}
            className="text-xs bg-lava border border-lava/60 text-geysirweiss/80 placeholder-geysirweiss/25 rounded-lg pl-2.5 pr-6 py-1 w-36 focus:outline-none focus:border-gletscherblau/40 focus:w-44 transition-all"
          />
          {search !== '' && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-geysirweiss/30 hover:text-geysirweiss/70 transition-colors leading-none"
              aria-label={t('library.searchReset')}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Ergebnis-Zähler */}
      <div className="text-geysirweiss/30 text-xs px-1 mb-3">
        {filtersActive
          ? t('library.videosFiltered', { shown: filtered.length, total: videos.length })
          : t('library.videos', { count: videos.length })}
      </div>

      {videos.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-14 text-center bg-lava/40 rounded-2xl border border-lava">
          <div className="text-4xl select-none opacity-40">📂</div>
          <p className="text-geysirweiss/40 text-sm">{t('library.empty')}</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center bg-lava/40 rounded-2xl border border-lava">
          <p className="text-geysirweiss/40 text-sm">{t('library.noMatch')}</p>
          <button
            onClick={() => { setGaitFilter('Alle'); setStatusFilter('Alle'); setSearch('') }}
            className="text-xs text-gletscherblau/70 hover:text-gletscherblau transition-colors underline underline-offset-2"
          >
            {t('library.resetFilter')}
          </button>
        </div>
      ) : (
        <ul className="space-y-3">
          {filtered.slice(0, visibleCount).map(entry => (
            <li
              key={entry.job_id}
              className={[
                'bg-lava rounded-xl border border-lava/80 px-5 py-4 flex items-center gap-4 transition-colors',
                entry.status === 'done' && onSelect
                  ? 'cursor-pointer hover:border-gletscherblau/40 hover:bg-lava/80'
                  : '',
              ].join(' ')}
              onClick={() => {
                if (entry.status === 'done' && onSelect) onSelect(entry)
              }}
            >
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-geysirweiss font-medium text-sm truncate max-w-xs">
                    {entry.horse_name ?? entry.filename}
                  </span>
                  {entry.horse_name && (
                    <span className="text-geysirweiss/35 text-xs truncate">{entry.filename}</span>
                  )}
                  {entry.is_training_contribution && (
                    <span className="text-nordlicht text-xs px-1.5 py-0.5 rounded bg-nordlicht/15 font-medium leading-none">
                      {t('library.trainingBadge')}
                    </span>
                  )}
                  {entry.training_consent && (
                    <span title={t('upload.trainingConsent')} className="text-nordlicht/70 text-xs px-1.5 py-0.5 rounded border border-nordlicht/30 font-medium leading-none">
                      {t('library.trainingConsentBadge')}
                    </span>
                  )}
                  {entry.is_annotated && (
                    <span className="text-gletscherblau text-xs px-1.5 py-0.5 rounded bg-islandblau/20 font-medium leading-none">
                      {t('library.annotatedBadge')}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 flex-wrap">
                  <span className={[
                    'text-xs px-2 py-0.5 rounded-full font-medium',
                    STATUS_COLOR[entry.status],
                  ].join(' ')}>
                    {t(STATUS_LABEL_KEY[entry.status])}
                  </span>

                  {/* Nutzer-Label: primäre Gangart-Anzeige */}
                  {entry.gait_label
                    ? entry.gait_label.split(',').map(g => g.trim()).filter(Boolean).map(g => (
                        <span key={g} className={[
                          'text-xs px-1.5 py-0.5 rounded font-medium',
                          g.toLowerCase() === 'tölt' || g.toLowerCase() === 'toelt'
                            ? 'text-nordlicht bg-nordlicht/10'
                            : 'text-gletscherblau bg-islandblau/15',
                        ].join(' ')}>
                          {g}
                        </span>
                      ))
                    : entry.gait_detected && entry.gait_detected !== 'Unbekannt' && (
                        <span className="text-xs text-gletscherblau/60">{entry.gait_detected}</span>
                      )
                  }

                  {/* KI-Abweichung: nur wenn KI zu anderem Ergebnis kam */}
                  {(() => {
                    const label = entry.gait_label
                    const det = entry.gait_detected
                    if (!label || label.includes(',') || !det || det === 'Unbekannt') return null
                    if (label.trim().toLowerCase() === det.toLowerCase()) return null
                    return (
                      <span
                        title={t('job.aiMismatchTooltip')}
                        className="text-xs px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-400/80 cursor-help"
                      >
                        ⚠ {t('job.aiMismatch', { gait: det })}
                      </span>
                    )
                  })()}


                  {entry.status === 'processing' && (
                    <span className="text-geysirweiss/40 text-xs">{entry.progress}%</span>
                  )}

                  <span className="text-geysirweiss/25 text-xs">{formatDate(entry.created_at)}</span>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
                {entry.status === 'done' && (<>
                  <a
                    href={getDownloadUrl(entry.job_id)}
                    download
                    className="text-xs px-3 py-1.5 rounded-lg bg-islandblau hover:bg-islandblau/80 text-geysirweiss transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {t('library.download')}
                  </a>
                  {reanalysingId === entry.job_id ? (
                    <span className="text-xs text-gletscherblau/60 px-1">{t('library.reanalysing')}</span>
                  ) : reanalyseOkId === entry.job_id ? (
                    <span className="text-xs text-nordlicht px-1">{t('library.reanalyseOk')}</span>
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); void handleReanalyse(entry.job_id) }}
                      className="text-xs px-3 py-1.5 rounded-lg border border-geysirweiss/15 text-geysirweiss/40 hover:text-gletscherblau hover:border-gletscherblau/40 transition-colors"
                      title="Gangart-Erkennung auf vorhandenen Keypoints erneut ausführen (kein Re-Upload)"
                    >
                      {t('library.reanalyse')}
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); setAnnotatingId(entry.job_id) }}
                    className="text-xs px-3 py-1.5 rounded-lg border border-geysirweiss/20 text-geysirweiss/60 hover:border-gletscherblau hover:text-gletscherblau transition-colors"
                  >
                    {t('library.annotate')}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingId(entry.job_id) }}
                    className="text-xs px-2.5 py-1.5 rounded-lg border border-geysirweiss/15 text-geysirweiss/40 hover:border-gletscherblau/50 hover:text-gletscherblau transition-colors"
                    title={t('metadata.title')}
                  >
                    ✏
                  </button>
                  <a
                    href={getExportUrl(entry.job_id)}
                    download={`toeltonaut_export_${entry.job_id.slice(0, 8)}.json`}
                    onClick={e => e.stopPropagation()}
                    className="text-xs px-3 py-1.5 rounded-lg border border-geysirweiss/15 text-geysirweiss/40 hover:text-geysirweiss/70 hover:border-geysirweiss/30 transition-colors"
                    title="Keypoints als COCO JSON exportieren"
                  >
                    {t('library.export')}
                  </a>
                  <a
                    href={getCocoZipUrl(entry.job_id)}
                    download={`toeltonaut_coco_${entry.job_id.slice(0, 8)}.zip`}
                    onClick={e => e.stopPropagation()}
                    className="text-xs px-3 py-1.5 rounded-lg border border-geysirweiss/15 text-geysirweiss/40 hover:text-geysirweiss/70 hover:border-geysirweiss/30 transition-colors"
                    title="COCO ZIP mit Frames + Keypoints für MMPose Fine-tuning"
                  >
                    COCO
                  </a>
                  {resettingId === entry.job_id ? (
                    <span className="text-xs text-geysirweiss/30 px-2">…</span>
                  ) : resetErrorId === entry.job_id ? (
                    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                      <span className="text-xs text-flaggenrot">{t('library.annotResetError')}</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); setResetErrorId(null); setConfirmResetId(entry.job_id) }}
                        className="text-xs px-2.5 py-1.5 rounded-lg bg-flaggenrot/20 text-flaggenrot hover:bg-flaggenrot/35 transition-colors"
                      >
                        {t('library.annotResetRetry')}
                      </button>
                    </div>
                  ) : confirmResetId === entry.job_id ? (
                    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                      <span className="text-xs text-flaggenrot/80">{t('library.annotResetConfirm')}</span>
                      <button
                        onClick={() => void handleResetAnnotations(entry.job_id)}
                        className="text-xs px-2.5 py-1.5 rounded-lg bg-flaggenrot/20 text-flaggenrot hover:bg-flaggenrot/35 transition-colors font-medium"
                      >
                        {t('library.annotResetYes')}
                      </button>
                      <button
                        onClick={() => setConfirmResetId(null)}
                        className="text-xs px-2.5 py-1.5 rounded-lg bg-geysirweiss/10 text-geysirweiss/50 hover:bg-geysirweiss/20 transition-colors"
                      >
                        {t('library.annotResetNo')}
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={e => { e.stopPropagation(); setConfirmResetId(entry.job_id) }}
                      className="text-xs px-3 py-1.5 rounded-lg border border-lava/80 text-geysirweiss/30 hover:text-flaggenrot/70 hover:border-flaggenrot/40 transition-colors"
                      title="Manuelle Annotationen löschen"
                    >
                      {t('library.annotReset')}
                    </button>
                  )}
                </>)}
                {(entry.status === 'processing' || entry.status === 'queued') && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingId(entry.job_id) }}
                    className="text-xs px-2.5 py-1.5 rounded-lg border border-geysirweiss/15 text-geysirweiss/40 hover:border-gletscherblau/50 hover:text-gletscherblau transition-colors"
                    title={t('metadata.title')}
                  >
                    ✏
                  </button>
                )}
                {deletingId === entry.job_id ? (
                  <span className="text-xs text-geysirweiss/30 px-2">…</span>
                ) : deleteErrorId === entry.job_id ? (
                  <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                    <span className="text-xs text-flaggenrot">{t('library.deleteError')}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteErrorId(null); setConfirmDeleteId(entry.job_id) }}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-flaggenrot/20 text-flaggenrot hover:bg-flaggenrot/35 transition-colors"
                    >
                      {t('library.deleteRetry')}
                    </button>
                  </div>
                ) : confirmDeleteId === entry.job_id ? (
                  <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                    <span className="text-xs text-flaggenrot/80">{t('library.deleteConfirm')}</span>
                    <button
                      onClick={() => void handleDelete(entry.job_id)}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-flaggenrot/20 text-flaggenrot hover:bg-flaggenrot/35 transition-colors font-medium"
                    >
                      {t('library.deleteYes')}
                    </button>
                    <button
                      onClick={() => setConfirmDeleteId(null)}
                      className="text-xs px-2.5 py-1.5 rounded-lg bg-geysirweiss/10 text-geysirweiss/50 hover:bg-geysirweiss/20 transition-colors"
                    >
                      {t('library.deleteNo')}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(entry.job_id) }}
                    className="text-xs px-3 py-1.5 rounded-lg border border-lava/80 text-flaggenrot/70 hover:text-flaggenrot hover:border-flaggenrot/40 transition-colors"
                  >
                    {t('library.delete')}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {visibleCount < filtered.length && (
        <div className="flex justify-center mt-4">
          <button
            onClick={() => setVisibleCount(n => n + 12)}
            className="text-xs px-4 py-2 rounded-lg border border-lava/60 text-geysirweiss/50 hover:border-gletscherblau/40 hover:text-geysirweiss/70 transition-colors"
          >
            {t('library.loadMore', { count: filtered.length - visibleCount })}
          </button>
        </div>
      )}
    </section>

    {annotatingId && (
      <AnnotationTool jobId={annotatingId} onClose={() => setAnnotatingId(null)} />
    )}
    {editingId && (() => {
      const entry = videos.find(e => e.job_id === editingId)
      return entry ? (
        <MetadataEditModal
          entry={entry}
          onSave={(updated) => handleMetadataSave(editingId, updated)}
          onClose={() => setEditingId(null)}
        />
      ) : null
    })()}
    </>
  )
}
