import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getJobStatus, deleteJob } from '../api/client'
import type { JobState } from '../types'
import TaktTimeline from './TaktTimeline'
import GaitSegmentBar from './GaitSegmentBar'
import ToltScoreCard from './ToltScoreCard'
import RennpassScoreCard from './RennpassScoreCard'
import VideoPlayer from './VideoPlayer'
import AnnotationTool from './AnnotationTool'

interface Props {
  jobId: string
  filename: string
  onReset: () => void
}

const GAIT_COLOR: Record<string, string> = {
  Tölt:      'text-nordlicht',
  Trab:      'text-gletscherblau',
  Schritt:   'text-gletscherblau',
  Galopp:    'text-gletscherblau',
  Rennpass:  'text-gletscherblau',
  Unbekannt: 'text-flaggenrot',
  '---':     'text-geysirweiss/40',
}

export default function JobProgress({ jobId, filename, onReset }: Props) {
  const { t } = useTranslation()
  const [job, setJob] = useState<JobState | null>(null)
  const [polling, setPolling] = useState(true)
  const [currentFrame, setCurrentFrame] = useState(0)
  const [showAnnotation, setShowAnnotation]   = useState(false)
  const [confirmDelete, setConfirmDelete]     = useState(false)
  const [deleteError, setDeleteError]         = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getJobStatus(jobId)
      setJob(data)
      if (data.status === 'done' || data.status === 'error') setPolling(false)
    } catch {
      setPolling(false)
    }
  }, [jobId])

  useEffect(() => { void fetchStatus() }, [fetchStatus])

  useEffect(() => {
    if (!polling) return
    const id = setInterval(() => { void fetchStatus() }, 1500)
    return () => clearInterval(id)
  }, [polling, fetchStatus])

  const handleDelete = async () => {
    setConfirmDelete(false)
    setDeleteError(false)
    try {
      await deleteJob(jobId)
      onReset()
    } catch {
      setDeleteError(true)
    }
  }

  if (!job) return (
    <div className="flex items-center justify-center h-32 text-geysirweiss/40 text-sm">
      {t('job.loadingStatus')}
    </div>
  )

  const isProcessing = job.status === 'processing' || job.status === 'queued'
  const isDone  = job.status === 'done'
  const isError = job.status === 'error'
  const gaitKey = job.gait_detected ?? '---'
  const gaitColor = GAIT_COLOR[gaitKey] ?? 'text-geysirweiss/50'

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="bg-lava rounded-2xl p-6 space-y-4">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-geysirweiss font-medium truncate">{filename}</div>
            <div className="text-geysirweiss/40 text-xs font-mono mt-0.5">{jobId.slice(0, 8)}</div>
          </div>
          <div className={[
            'shrink-0 text-sm font-medium px-3 py-1 rounded-full',
            isDone  ? 'bg-nordlicht/20 text-nordlicht' :
            isError ? 'bg-flaggenrot/20 text-flaggenrot' :
                      'bg-islandblau/20 text-gletscherblau',
          ].join(' ')}>
            {isDone ? t('job.done') : isError ? t('job.error') : t('job.analysing')}
          </div>
        </div>

        {/* Progress bar */}
        {isProcessing && (
          <div className="space-y-2">
            <div
              className="w-full bg-vulkan rounded-full h-2 overflow-hidden"
              role="progressbar"
              aria-valuenow={job.progress}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={t('job.progressLabel')}
            >
              <div
                className="bg-gradient-to-r from-islandblau to-nordlicht h-2 rounded-full transition-all duration-500"
                style={{ width: `${job.progress}%` }}
              />
            </div>
            <div aria-live="polite" aria-atomic="true" className="text-geysirweiss/60 text-sm">{job.message?.split(' – ')[0]}</div>
          </div>
        )}

        {/* Detected gait + camera angle */}
        {(isDone || isProcessing) && gaitKey !== '---' && (
          <div className="flex items-center gap-4 text-sm flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-geysirweiss/50">{t('job.detectedGait')}</span>
              <span className={`font-semibold ${gaitColor}`}>{gaitKey}</span>
            </div>
            {job.camera_angle && (
              <div className="flex items-center gap-2">
                <span className="text-geysirweiss/50">{t('job.cameraAngle')}</span>
                <span className="font-medium text-gletscherblau/80">{job.camera_angle.replace('_', ' ')}</span>
              </div>
            )}
          </div>
        )}

        {/* Error message */}
        {isError && (
          <div role="alert" className="text-flaggenrot-text text-sm bg-flaggenrot/10 rounded-lg p-3">
            {job.message}
          </div>
        )}

        {deleteError && (
          <div role="alert" className="text-flaggenrot-text text-xs bg-flaggenrot/10 rounded-lg px-3 py-2">
            {t('job.deleteError')}
          </div>
        )}

        {/* Actions */}
        {isDone && (
          <div className="flex gap-3 pt-2 flex-wrap items-center">
            <button
              onClick={() => setShowAnnotation(true)}
              className="px-4 py-2.5 rounded-xl border border-geysirweiss/20 text-geysirweiss/60 hover:border-gletscherblau hover:text-gletscherblau transition-colors text-sm"
            >
              {t('job.annotate')}
            </button>
            {confirmDelete ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-flaggenrot/80">{t('job.deletingConfirm')}</span>
                <button
                  onClick={() => void handleDelete()}
                  className="px-3 py-2 rounded-xl bg-flaggenrot/20 text-flaggenrot hover:bg-flaggenrot/30 transition-colors text-sm font-medium"
                >
                  {t('job.deletingYes')}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-3 py-2 rounded-xl border border-geysirweiss/20 text-geysirweiss/50 hover:border-gletscherblau hover:text-gletscherblau transition-colors text-sm"
                >
                  {t('common.cancel')}
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="px-4 py-2.5 rounded-xl border border-geysirweiss/20 text-geysirweiss/60 hover:border-flaggenrot hover:text-flaggenrot transition-colors text-sm"
              >
                {t('job.delete')}
              </button>
            )}
          </div>
        )}

        {showAnnotation && (
          <AnnotationTool jobId={jobId} onClose={() => setShowAnnotation(false)} />
        )}

        {isError && (
          <button
            onClick={onReset}
            className="w-full py-2.5 rounded-xl border border-geysirweiss/20 text-geysirweiss/60 hover:border-gletscherblau hover:text-gletscherblau transition-colors text-sm"
          >
            {t('job.newVideoAfterError')}
          </button>
        )}
      </div>

      {isDone && (
        <div className="mt-4 space-y-4">
          <VideoPlayer
            jobId={jobId}
            onTimeUpdate={setCurrentFrame}
            horseName={job.horse_name}
            speedMs={job.speed_ms}
            fps={job.output_fps ?? undefined}
          />
          {gaitKey === 'Rennpass' ? (
            <RennpassScoreCard jobId={jobId} />
          ) : (
            <ToltScoreCard jobId={jobId} />
          )}
          <GaitSegmentBar jobId={jobId} />
          <TaktTimeline jobId={jobId} currentFrame={currentFrame} />
        </div>
      )}
    </div>
  )
}
