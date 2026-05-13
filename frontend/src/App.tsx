import { useState, useCallback, Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'
import { useTranslation } from 'react-i18next'
import UploadZone from './components/UploadZone'
import LanguageSwitcher from './components/LanguageSwitcher'
import JobProgress from './components/JobProgress'
import VideoLibrary from './components/VideoLibrary'
import VideoPlayer from './components/VideoPlayer'
import ToltScoreCard from './components/ToltScoreCard'
import RennpassScoreCard from './components/RennpassScoreCard'
import TaktTimeline from './components/TaktTimeline'
import GaitSegmentBar from './components/GaitSegmentBar'
import RecordingGuide from './components/RecordingGuide'
import AdminPanel from './components/AdminPanel'
import VideoActions from './components/VideoActions'
import type { UploadResponse, VideoEntry } from './types'

class DetailErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[DetailErrorBoundary]', error, info.componentStack)
  }
  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="w-full max-w-2xl mx-auto p-6 bg-flaggenrot/20 border border-flaggenrot/40 rounded-xl text-flaggenrot-text text-sm space-y-2">
          <strong>Render error:</strong>
          <pre className="text-xs text-flaggenrot-text/80 whitespace-pre-wrap">{this.state.error.message}</pre>
          <button
            onClick={() => this.setState({ error: null })}
            className="text-xs text-geysirweiss/60 underline"
          >Reset</button>
        </div>
      )
    }
    return this.props.children
  }
}

interface ActiveJob {
  jobId: string
  filename: string
}

type Screen = 'home' | 'video-detail' | 'admin'

const HORSE_SVG = '/horse.svg'

export default function App() {
  const { t } = useTranslation()
  const [activeJob, setActiveJob]         = useState<ActiveJob | null>(null)
  const [screen, setScreen]               = useState<Screen>('home')
  const [selectedVideo, setSelectedVideo] = useState<VideoEntry | null>(null)
  const [detailFrame, setDetailFrame]     = useState(0)
  const [seekTarget, setSeekTarget]       = useState<{ ms: number; seq: number } | undefined>()
  const [detailFps, setDetailFps]         = useState<number | undefined>()

  const doSeek = useCallback((ms: number) => {
    setSeekTarget(prev => ({ ms, seq: (prev?.seq ?? 0) + 1 }))
  }, [])

  const handleJobStarted = (r: UploadResponse) => {
    setActiveJob({ jobId: r.job_id, filename: r.filename })
    setScreen('home')
  }

  const handleReset = () => setActiveJob(null)

  const handleSelectVideo = (entry: VideoEntry) => {
    setSelectedVideo(entry)
    setDetailFrame(0)
    setScreen('video-detail')
    window.scrollTo({ top: 0, behavior: 'instant' })
  }

  const handleBackToLibrary = () => {
    setSelectedVideo(null)
    setScreen('home')
    window.scrollTo({ top: 0, behavior: 'instant' })
  }

  return (
    <div className="min-h-screen bg-vulkan flex flex-col">
      <a href="#main-content" className="skip-link">Zum Hauptinhalt springen</a>

      {/* ── Header ── */}
      <header className="border-b border-lava/60 bg-vulkan/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => { setScreen('home'); setSelectedVideo(null); setActiveJob(null); window.scrollTo({ top: 0, behavior: 'instant' }) }}
            className="flex items-center gap-4 group"
          >
            <img src={HORSE_SVG} alt={t('app_screen.logoAlt')} className="h-10 w-auto opacity-90 group-hover:opacity-100 transition-opacity" />
            <div className="text-left">
              <h1 className="text-geysirweiss font-semibold text-xl leading-tight group-hover:text-gletscherblau transition-colors">
                Töltonaut
              </h1>
              <p className="text-gletscherblau text-xs">{t('app_screen.logoSubtitle')}</p>
            </div>
          </button>
          <div className="ml-auto flex items-center gap-3">
            <a
              href="/docs/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-3 py-1.5 rounded-lg text-geysirweiss/25 hover:text-gletscherblau hover:bg-lava/60 transition-colors"
              title="Dokumentation öffnen"
            >
              Docs
            </a>
            <button
              onClick={() => setScreen(s => s === 'admin' ? 'home' : 'admin')}
              className={[
                'text-xs px-3 py-1.5 rounded-lg transition-colors',
                screen === 'admin'
                  ? 'bg-flaggenrot/80 text-geysirweiss'
                  : 'text-geysirweiss/25 hover:text-geysirweiss/50 hover:bg-lava/60',
              ].join(' ')}
            >
              {t('app_screen.navAdmin')}
            </button>
            <LanguageSwitcher />
            <span className="text-geysirweiss/25 text-xs font-mono">v1.0</span>
          </div>
        </div>
      </header>

      {/* ── Hauptinhalt ── */}
      <main id="main-content" className="flex-1 flex flex-col items-center px-6 py-16 gap-12">

        {/* Video-Detail-Screen */}
        {screen === 'video-detail' && selectedVideo && (
          <DetailErrorBoundary>
          <div className="w-full max-w-4xl mx-auto space-y-6">
            <div className="flex items-center gap-3">
              <button
                onClick={handleBackToLibrary}
                className="text-gletscherblau/70 hover:text-gletscherblau text-sm transition-colors flex items-center gap-1"
              >
                {t('app_screen.backToLibrary')}
              </button>
              <span className="text-geysirweiss/30 text-sm">/</span>
              <span className="text-geysirweiss/60 text-sm truncate max-w-xs">
                {selectedVideo.horse_name ?? selectedVideo.filename}
              </span>
            </div>

            {/* Metadaten-Zeile */}
            {(selectedVideo.gait_label || selectedVideo.gait_detected || selectedVideo.horse_name) && (
              <div className="flex flex-wrap items-center gap-2 text-xs text-geysirweiss/45">
                {selectedVideo.horse_name && (
                  <span className="bg-lava px-2 py-0.5 rounded">{selectedVideo.horse_name}</span>
                )}
                {/* Nutzer-Label primär */}
                {selectedVideo.gait_label
                  ? selectedVideo.gait_label.split(',').map(g => g.trim()).filter(Boolean).map(g => (
                      <span key={g} className={[
                        'px-2 py-0.5 rounded',
                        g.toLowerCase() === 'tölt' || g.toLowerCase() === 'toelt'
                          ? 'text-nordlicht bg-nordlicht/10'
                          : 'bg-lava text-gletscherblau/80',
                      ].join(' ')}>
                        {g}
                      </span>
                    ))
                  : selectedVideo.gait_detected && (
                      <span className="bg-lava px-2 py-0.5 rounded text-gletscherblau/80">
                        {selectedVideo.gait_detected}
                      </span>
                    )
                }
                {/* KI-Abweichung */}
                {(() => {
                  const label = selectedVideo.gait_label
                  const det = selectedVideo.gait_detected
                  if (!label || label.includes(',') || !det || det === 'Unbekannt') return null
                  if (label.trim().toLowerCase() === det.toLowerCase()) return null
                  return (
                    <span
                      title={t('job.aiMismatchTooltip')}
                      className="px-2 py-0.5 rounded border border-amber-500/40 text-amber-400/80 text-xs cursor-help"
                    >
                      ⚠ {t('job.aiMismatch', { gait: det })}
                    </span>
                  )
                })()}
                {selectedVideo.training_consent && (
                  <span className="text-nordlicht/70 border border-nordlicht/30 px-2 py-0.5 rounded">✓ Training</span>
                )}
                <VideoActions jobId={selectedVideo.job_id} />
              </div>
            )}

            <VideoPlayer
              jobId={selectedVideo.job_id}
              onTimeUpdate={setDetailFrame}
              seekToMs={seekTarget}
              fps={selectedVideo.output_fps ?? detailFps}
              horseName={selectedVideo.horse_name}
              speedMs={selectedVideo.speed_ms}
            />

            <GaitSegmentBar jobId={selectedVideo.job_id} onSeek={doSeek} />

            {(selectedVideo.gait_detected?.toLowerCase() === 'rennpass') ? (
              <RennpassScoreCard jobId={selectedVideo.job_id} speedMs={selectedVideo.speed_ms ?? null} />
            ) : (
              <ToltScoreCard jobId={selectedVideo.job_id} speedMs={selectedVideo.speed_ms ?? null} />
            )}

            <TaktTimeline
              jobId={selectedVideo.job_id}
              currentFrame={detailFrame}
              onSeek={doSeek}
              onFpsDetected={setDetailFps}
            />
          </div>
          </DetailErrorBoundary>
        )}

        {/* Hauptseite: Upload + aktiver Job + Bibliothek */}
        {screen === 'home' && (
          <>
            {!activeJob && (
              <>
                <div className="text-center max-w-xl space-y-4">
                  <img src={HORSE_SVG} alt={t('app_screen.logoAlt')} className="h-28 mx-auto opacity-80 mb-2" />
                  <h2 className="text-geysirweiss text-3xl font-bold tracking-tight">
                    {t('app_screen.videoAnalyse')}
                  </h2>
                  <p className="text-geysirweiss/55 text-base leading-relaxed">
                    {t('app_screen.videoAnalyseDesc')}
                  </p>
                </div>

                <UploadZone onJobStarted={handleJobStarted} />
                <RecordingGuide />
              </>
            )}

            {activeJob && (
              <>
                <div className="text-center space-y-1">
                  <h2 className="text-geysirweiss text-2xl font-bold">{t('job.analysingRunning')}</h2>
                  <p className="text-geysirweiss/45 text-sm">{t('job.analysingHint')}</p>
                </div>
                <JobProgress
                  jobId={activeJob.jobId}
                  filename={activeJob.filename}
                  onReset={handleReset}
                />
                <button
                  onClick={handleReset}
                  className="text-geysirweiss/25 hover:text-geysirweiss/55 text-sm transition-colors"
                >
                  {t('job.newVideo')}
                </button>
              </>
            )}

            <VideoLibrary
              onSelect={handleSelectVideo}
            />
          </>
        )}

        {/* Admin-Screen */}
        {screen === 'admin' && (
          <div className="w-full max-w-xl mx-auto space-y-4">
            <div className="flex items-center gap-3">
              <button
                onClick={() => { setScreen('home'); window.scrollTo({ top: 0, behavior: 'instant' }) }}
                className="text-gletscherblau/70 hover:text-gletscherblau text-sm transition-colors flex items-center gap-1"
              >
                {t('app_screen.backToHome')}
              </button>
              <h2 className="text-geysirweiss/60 text-xs uppercase tracking-widest font-semibold">
                {t('app_screen.navAdmin')}
              </h2>
            </div>
            <AdminPanel onReset={() => { setActiveJob(null); setSelectedVideo(null); setScreen('home') }} />
          </div>
        )}

      </main>

      <footer className="border-t border-lava/40 py-4 text-center text-geysirweiss/20 text-xs">
        {t('app_screen.footer')}
      </footer>

    </div>
  )
}
