import type { AppStats, AuthTokens, CurrentUser, FrameKeypoints, GaitSegment, JobState, KeypointEntry, LearningStatus, RennpassScoreData, TaktTimeline, ToltScoreData, TrainingJobItem, TrainingStatusResponse, UploadResponse, VideoEntry } from '../types'
import { authHeader } from '../auth'

const BASE = ((import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_BASE) ?? '/api'

export interface UploadMeta {
  horse_name?: string
  gait_label?: string
  is_training_contribution?: boolean
  training_consent?: boolean
  stockmass_cm?: number
}

export async function uploadVideo(
  blob: Blob,
  filename: string,
  onProgress?: (pct: number) => void,
  meta?: UploadMeta,
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', blob, filename)
    if (meta?.horse_name) form.append('horse_name', meta.horse_name)
    if (meta?.gait_label) form.append('gait_label', meta.gait_label)
    if (meta?.is_training_contribution) form.append('is_training_contribution', 'true')
    if (meta?.training_consent) form.append('training_consent', 'true')
    if (meta?.stockmass_cm != null) form.append('stockmass_cm', String(meta.stockmass_cm))
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/upload`)
    const auth = authHeader() as Record<string, string>
    if (auth.Authorization) xhr.setRequestHeader('Authorization', auth.Authorization)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as UploadResponse)
      } else {
        let detail = `HTTP ${xhr.status}`
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string }
          if (body.detail) detail = body.detail
        } catch { /* ignorieren */ }
        reject(new Error(detail))
      }
    }
    xhr.onerror = () => reject(new Error(
      'Netzwerkfehler – Backend nicht erreichbar. Läuft der Server? (docker compose up)'
    ))
    xhr.send(form)
  })
}

export async function getJobStatus(jobId: string): Promise<JobState> {
  const res = await fetch(`${BASE}/status/${jobId}`)
  if (!res.ok) throw new Error(`Status-Abfrage fehlgeschlagen: ${res.status}`)
  return res.json() as Promise<JobState>
}

export async function deleteJob(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/job/${jobId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Löschen fehlgeschlagen: ${res.status}`)
}

export function getDownloadUrl(jobId: string): string {
  return `${BASE}/download/${jobId}`
}

export async function getVideos(): Promise<VideoEntry[]> {
  const res = await fetch(`${BASE}/videos`)
  if (!res.ok) throw new Error(`Video-Liste fehlgeschlagen: ${res.status}`)
  return res.json() as Promise<VideoEntry[]>
}

export async function getTaktTimeline(jobId: string): Promise<TaktTimeline> {
  const res = await fetch(`${BASE}/takt-timeline/${jobId}`)
  if (!res.ok) throw new Error('Timeline nicht verfügbar')
  return res.json() as Promise<TaktTimeline>
}


export async function getToltScore(jobId: string): Promise<ToltScoreData> {
  const res = await fetch(`${BASE}/toelt-score/${jobId}`)
  if (!res.ok) {
    const err = new Error('Tölt-Analyse nicht verfügbar') as Error & { status: number }
    err.status = res.status
    throw err
  }
  return res.json() as Promise<ToltScoreData>
}

export async function getRennpassScore(jobId: string): Promise<RennpassScoreData> {
  const res = await fetch(`${BASE}/rennpass-score/${jobId}`)
  if (!res.ok) {
    const err = new Error('Rennpass-Analyse nicht verfügbar') as Error & { status: number }
    err.status = res.status
    throw err
  }
  return res.json() as Promise<RennpassScoreData>
}

export async function register(email: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Registrierung fehlgeschlagen: ${res.status}`)
  }
  return res.json() as Promise<AuthTokens>
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const body = new URLSearchParams({ username: email, password })
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Anmeldung fehlgeschlagen: ${res.status}`)
  }
  return res.json() as Promise<AuthTokens>
}

export async function getMe(): Promise<CurrentUser> {
  const res = await fetch(`${BASE}/auth/me`, { headers: authHeader() })
  if (!res.ok) throw new Error(`Benutzer nicht abrufbar: ${res.status}`)
  return res.json() as Promise<CurrentUser>
}

export function getCocoExportUrl(jobId: string): string {
  return `${BASE}/export-coco/${jobId}`
}

export function getMetricsCsvUrl(jobId: string): string {
  return `${BASE}/metrics/${jobId}`
}

export async function getStats(): Promise<AppStats> {
  const res = await fetch(`${BASE}/stats`)
  if (!res.ok) throw new Error(`Stats nicht abrufbar: ${res.status}`)
  return res.json() as Promise<AppStats>
}

export async function getTrainingJobs(): Promise<TrainingJobItem[]> {
  const res = await fetch(`${BASE}/training/jobs`)
  if (!res.ok) throw new Error(`Training-Jobs nicht abrufbar: ${res.status}`)
  return res.json() as Promise<TrainingJobItem[]>
}

export async function createTrainingJob(
  model_version?: string,
  dataset_snapshot?: Record<string, unknown>,
): Promise<TrainingJobItem> {
  const res = await fetch(`${BASE}/training/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_version, dataset_snapshot }),
  })
  if (!res.ok) throw new Error(`Training-Job erstellen fehlgeschlagen: ${res.status}`)
  return res.json() as Promise<TrainingJobItem>
}

export function getFrameUrl(jobId: string, frameNr: number): string {
  return `${BASE}/frame/${jobId}/${frameNr}`
}

export async function getFrameKeypoints(jobId: string, frameNr: number, ms?: number): Promise<FrameKeypoints> {
  const url = ms !== undefined
    ? `${BASE}/keypoints/${jobId}/${frameNr}?ms=${ms}`
    : `${BASE}/keypoints/${jobId}/${frameNr}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Keypoints nicht abrufbar: ${res.status}`)
  return res.json() as Promise<FrameKeypoints>
}

export async function saveAnnotation(
  jobId: string,
  frameNr: number,
  keypoints: KeypointEntry[],
): Promise<void> {
  const res = await fetch(`${BASE}/annotations/${jobId}/${frameNr}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keypoints }),
  })
  if (!res.ok) throw new Error(`Annotation speichern fehlgeschlagen: ${res.status}`)
}

export async function getGaitSegments(jobId: string): Promise<GaitSegment[]> {
  const res = await fetch(`${BASE}/gait-segments/${jobId}`)
  if (!res.ok) throw new Error('Gangarten-Segmente nicht verfügbar')
  return res.json() as Promise<GaitSegment[]>
}

export async function getLearningStatus(): Promise<LearningStatus> {
  const res = await fetch(`${BASE}/learning-status`)
  if (!res.ok) throw new Error('Lernstatus nicht abrufbar')
  return res.json() as Promise<LearningStatus>
}

export function getExportUrl(jobId: string): string {
  return `${BASE}/export/${jobId}`
}

export function getCocoZipUrl(jobId: string): string {
  return `${BASE}/export-coco/${jobId}`
}

export function getAdminBackupFullUrl(): string {
  return `${BASE}/admin/backup/full`
}

export function getAdminBackupLearnedUrl(): string {
  return `${BASE}/admin/backup/learned`
}

export async function adminResetAll(): Promise<{ deleted_videos: number; deleted_files: number }> {
  const res = await fetch(`${BASE}/admin/reset`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Admin-Reset fehlgeschlagen: ${res.status}`)
  return res.json() as Promise<{ deleted_videos: number; deleted_files: number }>
}

export function getBulkCocoExportUrl(): string {
  return `${BASE}/training/export-bulk`
}

export async function resetAnnotations(jobId: string): Promise<{ deleted: number }> {
  const res = await fetch(`${BASE}/annotations/${jobId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Annotationen konnten nicht zurückgesetzt werden')
  return res.json() as Promise<{ deleted: number }>
}

export async function updateVideoMetadata(jobId: string, data: {
  horse_name?: string
  gait_label?: string
  camera_angle?: string
  training_consent?: boolean
}): Promise<void> {
  const res = await fetch(`${BASE}/job/${jobId}/metadata`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(authHeader() as Record<string, string>) },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
}

export async function deleteAccount(): Promise<{ deleted: string }> {
  const res = await fetch(`${BASE}/auth/account`, {
    method: 'DELETE',
    headers: authHeader(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Account-Löschung fehlgeschlagen: ${res.status}`)
  }
  return res.json() as Promise<{ deleted: string }>
}

export async function startTraining(): Promise<TrainingJobItem> {
  const res = await fetch(`${BASE}/training/start`, {
    method: 'POST',
    headers: authHeader() as Record<string, string>,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Training starten fehlgeschlagen: ${res.status}`)
  }
  return res.json() as Promise<TrainingJobItem>
}

export async function getTrainingStatus(jobId: number): Promise<TrainingStatusResponse> {
  const res = await fetch(`${BASE}/training/status/${jobId}`)
  if (!res.ok) throw new Error(`Training-Status nicht abrufbar: ${res.status}`)
  return res.json() as Promise<TrainingStatusResponse>
}

export async function reanalyseJob(jobId: string): Promise<{
  job_id: string
  updated_frames: number
  total_frames: number
  dominant_gait: string | null
}> {
  const res = await fetch(`${BASE}/job/${jobId}/reanalyse`, {
    method: 'POST',
    headers: authHeader() as Record<string, string>,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Neuanalyse fehlgeschlagen: ${res.status}`)
  }
  return res.json()
}

export async function activateModel(jobId: number): Promise<{ activated: string; job_id: number }> {
  const res = await fetch(`${BASE}/training/activate/${jobId}`, {
    method: 'POST',
    headers: authHeader() as Record<string, string>,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Modell aktivieren fehlgeschlagen: ${res.status}`)
  }
  return res.json() as Promise<{ activated: string; job_id: number }>
}
