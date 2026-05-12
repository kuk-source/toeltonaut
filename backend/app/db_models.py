from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    videos: Mapped[list["Video"]] = relationship("Video", back_populates="user")


class Video(Base):
    __tablename__ = "videos"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False, default="")
    horse_name: Mapped[str | None] = mapped_column(String, nullable=True)
    gait_label: Mapped[str | None] = mapped_column(String, nullable=True)
    camera_angle: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    gait_detected: Mapped[str | None] = mapped_column(String, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str] = mapped_column(String, nullable=False, default="Warte auf Verarbeitung...")
    output_path: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    is_training_contribution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stockmass_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User | None"] = relationship("User", back_populates="videos")
    frames: Mapped[list["Frame"]] = relationship("Frame", back_populates="video", cascade="all, delete-orphan")


class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (
        Index("ix_frames_video_frame", "video_id", "frame_nr"),
        UniqueConstraint("video_id", "frame_nr", name="uq_frames_video_frame"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(String, ForeignKey("videos.job_id", ondelete="CASCADE"), nullable=False)
    frame_nr: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    gait: Mapped[str | None] = mapped_column(String, nullable=True)
    is_side_view: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    video: Mapped["Video"] = relationship("Video", back_populates="frames")
    keypoints: Mapped[list["Keypoint"]] = relationship("Keypoint", back_populates="frame", cascade="all, delete-orphan")
    annotations: Mapped[list["Annotation"]] = relationship("Annotation", back_populates="frame", cascade="all, delete-orphan")


class Keypoint(Base):
    __tablename__ = "keypoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    frame_id: Mapped[int] = mapped_column(Integer, ForeignKey("frames.id", ondelete="CASCADE"), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    frame: Mapped["Frame"] = relationship("Frame", back_populates="keypoints")


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    frame_id: Mapped[int] = mapped_column(Integer, ForeignKey("frames.id", ondelete="CASCADE"), nullable=False)
    keypoints: Mapped[dict] = mapped_column(JSONB, nullable=False)
    quality_flag: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    annotator: Mapped[str | None] = mapped_column(Text, nullable=True)

    frame: Mapped["Frame"] = relationship("Frame", back_populates="annotations")


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
