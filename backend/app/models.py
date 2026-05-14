from datetime import datetime
from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class JobState(BaseModel):
    job_id: str
    input_path: str
    output_path: str
    filename: str = ""
    horse_name: Optional[str] = None
    gait_label: Optional[str] = None
    camera_angle: Optional[str] = None
    status: str = "queued"
    progress: int = 0
    message: str = "Warte auf Verarbeitung..."
    gait_detected: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[int] = None
    is_training_contribution: bool = False
    training_consent: bool = False
    stockmass_cm: Optional[int] = None
    speed_ms: Optional[float] = None
    output_fps: Optional[float] = None

    model_config = {"arbitrary_types_allowed": True}


class UploadResponse(BaseModel):
    job_id: str
    filename: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    gait_detected: Optional[str] = None
    horse_name: Optional[str] = None
    gait_label: Optional[str] = None
    camera_angle: Optional[str] = None
    stockmass_cm: Optional[int] = None
    speed_ms: Optional[float] = None
    output_fps: Optional[float] = None


class VideoListItem(BaseModel):
    job_id: str
    filename: str
    horse_name: Optional[str] = None
    gait_label: Optional[str] = None
    camera_angle: Optional[str] = None
    status: str
    gait_detected: Optional[str] = None
    progress: int
    message: str
    created_at: str
    is_training_contribution: bool = False
    training_consent: bool = False
    is_annotated: bool = False
    stockmass_cm: Optional[int] = None
    speed_ms: Optional[float] = None
    output_fps: Optional[float] = None


class TaktTrackPoint(BaseModel):
    frame: int
    y_norm: float


class TaktTimelineResponse(BaseModel):
    job_id: str
    fps: float
    total_frames: int
    tracks: Dict[str, List[TaktTrackPoint]]
    non_side_view_frames: List[int] = []


class ToltErrorModel(BaseModel):
    type: str
    severity: str
    frame_range: List[int]
    description: str


class ToltScoreResponse(BaseModel):
    job_id: str
    score: float
    feif_grade: str
    errors: List[ToltErrorModel]
    takt_regularity: float
    beat_count: int
    disclaimer: str
    lap: Optional[float] = None
    df: Optional[float] = None
    subclassification: Optional[str] = None


class RennpassErrorModel(BaseModel):
    type: str
    severity: str
    frame_range: List[int]
    description: str


class RennpassScoreResponse(BaseModel):
    job_id: str
    score: float
    feif_grade: str
    errors: List[RennpassErrorModel]
    lateral_sync: float
    suspension_detected: bool
    stride_count: int
    disclaimer: str


class RegisterRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    id: int
    email: str
    created_at: datetime


class AppStats(BaseModel):
    total_videos: int
    done_videos: int
    training_contributions: int
    gait_distribution: Dict[str, int]
    avg_toelt_score: Optional[float] = None


class LearningStatus(BaseModel):
    model_version: str
    total_videos: int
    training_videos: int
    total_frames: int
    annotated_frames: int
    gait_distribution: Dict[str, int]


class TrainingJobItem(BaseModel):
    id: int
    model_version: Optional[str] = None
    mlflow_run_id: Optional[str] = None
    metrics: Optional[dict] = None
    created_at: str
    status: Optional[str] = None         # queued | running | done | error (nur laufende Jobs)
    epoch: Optional[int] = None
    total_epochs: Optional[int] = None


class TrainingStatusResponse(BaseModel):
    job_id: int
    status: str                           # queued | running | done | error
    epoch: int
    total_epochs: int
    loss: float
    message: str


class CreateTrainingJobRequest(BaseModel):
    model_version: Optional[str] = None
    dataset_snapshot: Optional[dict] = None


class KeypointEntry(BaseModel):
    name: str
    x: float
    y: float
    confidence: float


class FrameKeypoints(BaseModel):
    keypoints: List[KeypointEntry]
    gait: Optional[str] = None
    speed_ms: Optional[float] = None


class GaitSegment(BaseModel):
    gait: str
    start_frame: int
    end_frame: int
    start_ms: float
    end_ms: float
    frame_count: int


class VideoMetadataUpdate(BaseModel):
    horse_name: Optional[str] = None
    gait_label: Optional[str] = None
    camera_angle: Optional[str] = None
    training_consent: Optional[bool] = None

