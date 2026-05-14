export type JobStatus = 'queued' | 'processing' | 'done' | 'error'

export interface JobState {
  job_id: string
  status: JobStatus
  progress: number
  message: string
  gait_detected: string | null
  gait_label: string | null
  camera_angle: string | null
  stockmass_cm?: number | null
  horse_name?: string | null
  speed_ms?: number | null
  output_fps?: number | null
}

export interface UploadResponse {
  job_id: string
  filename: string
}

export interface TaktFrame {
  frame: number
  y_norm: number
}

export interface TaktTimeline {
  job_id: string
  fps: number
  total_frames: number
  tracks: {
    VL: TaktFrame[]
    VR: TaktFrame[]
    HL: TaktFrame[]
    HR: TaktFrame[]
  }
  non_side_view_frames?: number[]
}


export interface VideoEntry {
  job_id: string
  filename: string
  horse_name: string | null
  gait_label: string | null
  camera_angle: string | null
  status: 'queued' | 'processing' | 'done' | 'error' | 'expired'
  gait_detected: string | null
  progress: number
  message: string
  created_at: string
  is_training_contribution?: boolean
  training_consent?: boolean
  is_annotated?: boolean
  stockmass_cm?: number | null
  speed_ms?: number | null
  output_fps?: number | null
}

export interface ToltError {
  type: string
  severity: 'schwer' | 'mittel' | 'leicht'
  frame_range: [number, number]
  description: string
}

export interface ToltScoreData {
  job_id: string
  score: number
  feif_grade: string
  errors: ToltError[]
  takt_regularity: number
  beat_count: number
  disclaimer: string
  /** LAP = Lateral Advanced Placement in % (0–50), optional ab v0.2 */
  lap?: number | null
  /** DF = Duty Factor in % (0–100), optional ab v0.2 */
  df?: number | null
  /** Tölt-Subklassifikation: 'correct' | 'passig' | 'trabig' | null */
  subclassification?: string | null
}

export interface RennpassError {
  type: string
  severity: 'schwer' | 'mittel' | 'leicht'
  frame_range: [number, number]
  description: string
}

export interface RennpassScoreData {
  job_id: string
  score: number
  feif_grade: string
  errors: RennpassError[]
  lateral_sync: number
  suspension_detected: boolean
  stride_count: number
  disclaimer: string
}

export interface AuthTokens {
  access_token: string
  token_type: string
}

export interface CurrentUser {
  id: number
  email: string
  created_at: string
}

export interface AppStats {
  total_videos: number
  done_videos: number
  training_contributions: number
  gait_distribution: Record<string, number>
  avg_toelt_score: number | null
}

export interface TrainingJobItem {
  id: number
  model_version: string | null
  mlflow_run_id: string | null
  metrics: Record<string, unknown> | null
  created_at: string
  status?: 'queued' | 'running' | 'done' | 'error'
  epoch?: number
  total_epochs?: number
}

export interface TrainingStatusResponse {
  job_id: number
  status: 'queued' | 'running' | 'done' | 'error'
  epoch: number
  total_epochs: number
  loss: number
  message: string
}

export interface KeypointEntry {
  name: string
  x: number
  y: number
  confidence: number
}

export interface FrameKeypoints {
  keypoints: KeypointEntry[]
  gait?: string | null
  speed_ms?: number | null
}

export interface GaitSegment {
  gait: string
  start_frame: number
  end_frame: number
  start_ms: number
  end_ms: number
  frame_count: number
}

export interface LearningStatus {
  model_version: string
  total_videos: number
  training_videos: number
  total_frames: number
  annotated_frames: number
  gait_distribution: Record<string, number>
}
