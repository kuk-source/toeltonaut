import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getTrainingJobs, getVideos, getCocoExportUrl, getBulkCocoExportUrl, startTraining, getTrainingStatus, activateModel, getLearningStatus } from '../api/client'
import type { LearningStatus, TrainingJobItem, TrainingStatusResponse, VideoEntry } from '../types'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

// Sprint J1: Workflow-Entscheidung
// POST /api/training/start liest Videos mit training_consent=True direkt aus der DB und
// erstellt intern das COCO-ZIP. Der separate Export-Endpunkt ist nur ein Download für den
// Nutzer. Der 1-Klick-Button braucht daher KEINEN vorherigen Export-Schritt –
// ein einziger startTraining()-Call reicht für den kombinierten Workflow.

type OneClickPhase = 'idle' | 'starting' | 'running'

export default function TrainingManager() {
  const { t } = useTranslation()
  const [jobs, setJobs] = useState<TrainingJobItem[]>([])
  const [contributions, setContributions] = useState<VideoEntry[]>([])
  const [learningStatus, setLearningStatus] = useState<LearningStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTrainingId, setActiveTrainingId] = useState<number | null>(null)
  const [trainingStatus, setTrainingStatus] = useState<TrainingStatusResponse | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [activatingId, setActivatingId] = useState<number | null>(null)
  // 1-Klick-Workflow: zeigt mehrstufigen Status
  const [oneClickPhase, setOneClickPhase] = useState<OneClickPhase>('idle')

  const fetchData = useCallback(async () => {
    try {
      const [jobsData, videosData, statusData] = await Promise.all([
        getTrainingJobs(),
        getVideos(),
        getLearningStatus().catch(() => null),
      ])
      setJobs(jobsData)
      setContributions(
        videosData.filter(v => v.is_training_contribution && v.status === 'done')
      )
      setLearningStatus(statusData)
    } catch {
      // stale data bleibt sichtbar
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  // 1-Klick-Workflow: Training direkt starten (kein separater Export nötig –
  // POST /api/training/start baut das COCO-ZIP intern aus der DB).
  const handleOneClickTraining = async () => {
    setStartError(null)
    setOneClickPhase('starting')
    try {
      const job = await startTraining()
      setActiveTrainingId(job.id)
      setOneClickPhase('running')
      void fetchData()
    } catch (e) {
      setStartError(e instanceof Error ? e.message : 'Unbekannter Fehler')
      setOneClickPhase('idle')
    }
  }

  // Direkter Training-Start (aus den erweiterten Optionen)
  const handleStartTraining = async () => {
    setStartError(null)
    try {
      const job = await startTraining()
      setActiveTrainingId(job.id)
      void fetchData()
    } catch (e) {
      setStartError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    }
  }

  // Polling alle 2 s solange Training läuft
  useEffect(() => {
    if (!activeTrainingId) return
    const poll = async () => {
      try {
        const status = await getTrainingStatus(activeTrainingId)
        setTrainingStatus(status)
        if (status.status === 'done' || status.status === 'error') {
          setActiveTrainingId(null)
          setOneClickPhase('idle')
          void fetchData()
        }
      } catch { /* ignorieren */ }
    }
    void poll()
    const id = setInterval(() => void poll(), 2000)
    return () => clearInterval(id)
  }, [activeTrainingId, fetchData])

  const handleActivate = async (jobId: number) => {
    setActivatingId(jobId)
    try {
      await activateModel(jobId)
      void fetchData()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Aktivierung fehlgeschlagen')
    } finally {
      setActivatingId(null)
    }
  }

  if (loading) {
    return (
      <div className="w-full max-w-2xl mx-auto">
        <div className="text-geysirweiss/30 text-sm text-center py-8">{t('training.loading')}</div>
      </div>
    )
  }

  const isTrainingActive = !!activeTrainingId
  const canStartTraining = contributions.length > 0 && !isTrainingActive

  // Mehrstufige Status-Beschriftung für den 1-Klick-Button
  const oneClickLabel = (() => {
    if (oneClickPhase === 'starting') return t('training.oneClickPhase1')
    if (oneClickPhase === 'running') {
      if (trainingStatus?.status === 'queued') return t('training.trainingStarting')
      if (trainingStatus && trainingStatus.total_epochs > 0) {
        const pct = Math.round((trainingStatus.epoch / trainingStatus.total_epochs) * 100)
        return t('training.oneClickPhase2Pct', { pct })
      }
      return t('training.oneClickPhase2')
    }
    return t('training.oneClickStart')
  })()

  return (
    <div className="w-full max-w-2xl mx-auto space-y-8">

      {/* === 1-Klick-Training (Primär-Aktion) === */}
      <section className="bg-lava/40 border border-islandblau/20 rounded-2xl px-6 py-6 space-y-4">
        <div>
          <h3 className="text-geysirweiss font-semibold text-base mb-1">
            {t('training.oneClickTitle')}
          </h3>
          <p className="text-geysirweiss/50 text-xs">
            {contributions.length > 0
              ? t('training.oneClickVideosAvailable', { count: contributions.length })
              : t('training.oneClickNoVideos')}
          </p>
        </div>

        <button
          onClick={() => void handleOneClickTraining()}
          disabled={!canStartTraining}
          className="w-full py-3 px-5 rounded-xl font-semibold text-sm
            bg-gradient-to-r from-islandblau to-nordlicht/80 text-white
            hover:from-islandblau/90 hover:to-nordlicht/70
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-all duration-200 shadow-md"
        >
          {oneClickLabel}
        </button>

        {/* Fortschrittsbalken für 1-Klick-Workflow */}
        {(oneClickPhase === 'running') && trainingStatus && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gletscherblau font-medium">
                {trainingStatus.status === 'queued'
                  ? t('training.trainingStarting')
                  : t('training.trainingEpoch', { epoch: trainingStatus.epoch, total: trainingStatus.total_epochs })}
              </span>
              {trainingStatus.loss > 0 && (
                <span className="text-geysirweiss/40 font-mono">
                  Loss: {trainingStatus.loss.toFixed(5)}
                </span>
              )}
            </div>
            <div className="w-full bg-vulkan rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-islandblau to-nordlicht h-1.5 rounded-full transition-all duration-700"
                style={{
                  width: trainingStatus.total_epochs > 0
                    ? `${(trainingStatus.epoch / trainingStatus.total_epochs) * 100}%`
                    : '10%'
                }}
              />
            </div>
          </div>
        )}

        {trainingStatus?.status === 'error' && (
          <div role="alert" className="bg-flaggenrot/10 border border-flaggenrot/30 rounded-xl px-4 py-3 text-flaggenrot-text text-sm">
            {t('training.trainingError', { message: trainingStatus.message })}
          </div>
        )}

        {startError && (
          <div role="alert" className="bg-flaggenrot/10 border border-flaggenrot/30 rounded-xl px-4 py-3 text-flaggenrot-text text-sm">
            {startError}
          </div>
        )}
      </section>

      {/* Training-Jobs */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-geysirweiss/60 text-xs uppercase tracking-widest font-semibold">
            {t('training.trainingJobsTitle')}
          </h3>
        </div>

        {jobs.length === 0 ? (
          <div className="bg-lava/40 border border-lava rounded-2xl px-6 py-8 text-center">
            <p className="text-geysirweiss/40 text-sm">
              {t('training.noJobs')}
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {jobs.map(job => (
              <li
                key={job.id}
                className="bg-lava rounded-xl border border-lava/80 px-5 py-4 space-y-2"
              >
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-geysirweiss font-medium text-sm truncate">
                      {job.model_version ?? <span className="text-geysirweiss/40 italic">{t('training.modelNoTag')}</span>}
                    </span>
                    {learningStatus?.model_version && job.model_version === learningStatus.model_version && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-nordlicht/20 text-nordlicht font-semibold shrink-0">
                        {t('training.modelActiveBadge')}
                      </span>
                    )}
                  </div>
                  <span className="text-geysirweiss/35 text-xs shrink-0">{formatDate(job.created_at)}</span>
                </div>

                <div className="flex items-center gap-3 flex-wrap">
                  {job.mlflow_run_id && (
                    <span className="text-gletscherblau text-xs font-mono bg-islandblau/20 px-2 py-0.5 rounded">
                      MLflow: {job.mlflow_run_id.slice(0, 12)}…
                    </span>
                  )}
                  {job.metrics && Object.keys(job.metrics).length > 0 && (
                    <span className="text-nordlicht text-xs font-mono bg-nordlicht/10 px-2 py-0.5 rounded">
                      loss={String((job.metrics as Record<string, unknown>).train_loss ?? '–')}
                      {' · '}
                      {String((job.metrics as Record<string, unknown>).epochs_run ?? '?')} Epochen
                    </span>
                  )}
                  {!job.mlflow_run_id && !job.metrics && (
                    <span className="text-geysirweiss/30 text-xs">{t('training.modelNoMetrics')}</span>
                  )}
                </div>

                {/* Aktivieren/Rollback-Button: nur wenn Training abgeschlossen (Metriken vorhanden) */}
                {job.metrics && (() => {
                  const isActive = learningStatus?.model_version != null && job.model_version === learningStatus.model_version
                  const isRollback = jobs.indexOf(job) > 0  // nicht der neueste
                  return (
                    <div className="pt-1">
                      {isActive ? (
                        <span className="text-xs px-3 py-1.5 rounded-lg bg-nordlicht/10 text-nordlicht/60 select-none">
                          {t('training.modelActive')}
                        </span>
                      ) : (
                        <button
                          onClick={() => void handleActivate(job.id)}
                          disabled={activatingId === job.id}
                          className="text-xs px-3 py-1.5 rounded-lg bg-nordlicht/20 text-nordlicht hover:bg-nordlicht/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          {activatingId === job.id
                            ? t('training.modelActivating')
                            : isRollback ? t('training.modelRollback') : t('training.modelActivate')}
                        </button>
                      )}
                    </div>
                  )
                })()}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Erweiterte Optionen */}
      <section>
        <details className="group">
          <summary className="cursor-pointer list-none flex items-center gap-2 text-geysirweiss/40 hover:text-geysirweiss/60 text-xs uppercase tracking-widest font-semibold transition-colors select-none">
            <span className="group-open:rotate-90 transition-transform duration-200 inline-block">▶</span>
            {t('training.trainingAdvanced')}
          </summary>

          <div className="mt-4 space-y-6 pl-4 border-l border-lava/60">

            {/* Manueller Training-Start */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-geysirweiss/60 text-xs font-semibold">{t('training.trainingFineTune')}</span>
                <button
                  onClick={() => void handleStartTraining()}
                  disabled={isTrainingActive}
                  className="text-xs px-3 py-1.5 rounded-lg bg-islandblau/20 text-gletscherblau hover:bg-islandblau/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {isTrainingActive ? t('training.trainingRunning') : t('training.trainingFineTuneButton')}
                </button>
              </div>
              <p className="text-geysirweiss/30 text-xs">{t('training.trainingFineTuneHint')}</p>
            </div>

            {/* COCO-Export */}
            {contributions.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-geysirweiss/60 text-xs font-semibold">{t('training.cocoExport')}</span>
                  <a
                    href={getBulkCocoExportUrl()}
                    download
                    className="text-xs px-3 py-1.5 rounded-lg bg-nordlicht/20 text-nordlicht hover:bg-nordlicht/30 transition-colors shrink-0"
                  >
                    {t('training.trainingPackageExport', { count: contributions.length })}
                  </a>
                </div>
                <ul className="space-y-2">
                  {contributions.map(video => (
                    <li
                      key={video.job_id}
                      className="bg-lava/60 border border-lava rounded-xl px-4 py-3 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <span className="text-geysirweiss text-sm truncate block">
                          {video.horse_name ?? video.filename}
                        </span>
                        {video.gait_label && (
                          <span className="text-nordlicht text-xs">{video.gait_label}</span>
                        )}
                      </div>
                      <a
                        href={getCocoExportUrl(video.job_id)}
                        download
                        className="text-xs px-3 py-1.5 rounded-lg bg-nordlicht/20 text-nordlicht hover:bg-nordlicht/30 transition-colors shrink-0"
                      >
                        COCO-JSON
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

          </div>
        </details>
      </section>

    </div>
  )
}
