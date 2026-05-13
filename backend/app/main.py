import asyncio
import csv
import io
import json
import logging
import os
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import BackgroundTasks, Body, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import create_access_token, get_current_user, get_optional_user, hash_password, verify_password
from .config import CORS_ORIGINS, DATABASE_URL, MAX_UPLOAD_MB, MODELS_DIR, OUTPUT_TTL_HOURS, UPLOAD_TTL_HOURS, OUTPUTS_DIR, UPLOADS_DIR, SECRET_KEY, VID_STRIDE, _DEFAULT_SECRET
from .database import get_db, init_db
from .db_models import Annotation, Frame, Keypoint, TrainingJob, User, Video
from .models import (
    AppStats, CreateTrainingJobRequest, FrameKeypoints, GaitSegment, JobState, JobStatus,
    KeypointEntry, LearningStatus, RegisterRequest, RennpassErrorModel, RennpassScoreResponse,
    TaktTimelineResponse, TaktTrackPoint, ToltErrorModel, ToltScoreResponse, TokenResponse,
    TrainingJobItem, TrainingStatusResponse, UploadResponse, UserMe, VideoListItem, VideoMetadataUpdate,
)
from .rennpass_scorer import RennpassScorer
from .tolt_scorer import ToltScorer
from .video_processor import get_processor

logger = logging.getLogger(__name__)

_DB_URL_SYNC = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)

app = FastAPI(title="Töltonaut API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dokumentation als statische Dateien: /docs/* → docs/-Ordner im Projekt
_DOCS_CANDIDATES = [
    Path(os.getenv("DOCS_DIR", "")),
    Path(__file__).parent.parent.parent / "docs",   # dev: Töltonaut/docs
    Path("/app/docs"),                               # Docker-Volume-Mount
]
_DOCS_DIR = next((p for p in _DOCS_CANDIDATES if p and p.is_dir()), None)
if _DOCS_DIR:
    app.mount("/docs", StaticFiles(directory=str(_DOCS_DIR)), name="docs")

jobs: dict[str, JobState] = {}
_lock = threading.Lock()

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I
)

def _require_job_id(job_id: str) -> None:
    if not _UUID_RE.match(job_id):
        raise HTTPException(400, "Ungültige Job-ID.")


def _migrate_add_training_columns() -> None:
    """Fügt is_training_contribution und training_consent zur videos-Tabelle hinzu,
    falls sie noch nicht existieren (kein Alembic, ALTER TABLE IF NOT EXISTS)."""
    try:
        import psycopg  # type: ignore
        with psycopg.connect(_DB_URL_SYNC) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS "
                    "is_training_contribution BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cur.execute(
                    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS "
                    "training_consent BOOLEAN NOT NULL DEFAULT FALSE"
                )
            conn.commit()
    except Exception:
        logger.exception("Migration für Training-Spalten fehlgeschlagen")


def _migrate_add_side_view_column() -> None:
    """Fügt is_side_view zur frames-Tabelle hinzu (idempotent)."""
    try:
        import psycopg  # type: ignore
        with psycopg.connect(_DB_URL_SYNC) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE frames ADD COLUMN IF NOT EXISTS "
                    "is_side_view BOOLEAN"
                )
            conn.commit()
    except Exception:
        logger.exception("Migration für is_side_view fehlgeschlagen")


def _migrate_add_frame_unique_constraint() -> None:
    """Fügt Unique-Constraint (video_id, frame_nr) zur frames-Tabelle hinzu (idempotent)."""
    try:
        import psycopg  # type: ignore
        with psycopg.connect(_DB_URL_SYNC) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'uq_frames_video_frame'
                        ) THEN
                            ALTER TABLE frames
                            ADD CONSTRAINT uq_frames_video_frame UNIQUE (video_id, frame_nr);
                        END IF;
                    END $$;
                """)
            conn.commit()
    except Exception:
        logger.exception("Migration für frames-Unique-Constraint fehlgeschlagen")


@app.on_event("startup")
async def startup() -> None:
    if SECRET_KEY == _DEFAULT_SECRET:
        logger.warning("⚠ SECRET_KEY ist der Standard-Entwicklungswert – bitte in .env setzen!")
    await init_db()
    _migrate_add_training_columns()
    _migrate_add_frame_unique_constraint()
    _migrate_add_side_view_column()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _recover_completed_jobs)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_GAITS = {"Tölt", "Trab", "Schritt", "Galopp", "Rennpass", "Gemischt"}
ALLOWED_ANGLES = {
    "Seitenansicht links", "Seitenansicht rechts",
    "Schräg von vorne", "Schräg von hinten", "Frontalansicht",
}

# Normalisierungstabellen – akzeptieren Lowercase/ASCII-Varianten aus dem Frontend
_GAIT_NORMALIZE: dict[str, str] = {
    "toelt": "Tölt", "tölt": "Tölt", "tolt": "Tölt",
    "trab": "Trab",
    "schritt": "Schritt",
    "galopp": "Galopp",
    "rennpass": "Rennpass",
}
_ANGLE_NORMALIZE: dict[str, str] = {
    "schraeg_vorn":    "schräg_vorn",
    "schraeg_hinten":  "schräg_hinten",
    "schräg_vorn":     "schräg_vorn",
    "schräg_hinten":   "schräg_hinten",
    "seitlich_links":  "seitlich_links",
    "seitlich_rechts": "seitlich_rechts",
}


def _normalize_gait(value: str | None) -> str | None:
    if not value:
        return None
    return _GAIT_NORMALIZE.get(value.lower(), value)


def _normalize_angle(value: str | None) -> str | None:
    if not value:
        return None
    return _ANGLE_NORMALIZE.get(value.lower(), value)


def _recover_completed_jobs() -> None:
    """Stellt Jobs aus DB (primär) + Dateisystem (Fallback) wieder her.

    DB ist die einzige persistente Quelle. Wird im startup-Event nach init_db()
    aufgerufen – dort existieren die Tabellen bereits garantiert.
    Für Videos, die nur auf dem Dateisystem liegen (alt, vor DB-Einführung),
    wird nachträglich ein DB-Eintrag angelegt, damit Annotationen funktionieren.
    """
    import psycopg  # type: ignore

    db_job_ids: set[str] = set()

    # ── 1. Primär: aus DB laden ──────────────────────────────────────────────
    try:
        with psycopg.connect(_DB_URL_SYNC) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT job_id, filename, horse_name, gait_label, camera_angle,
                           gait_detected, output_path, created_at,
                           COALESCE(is_training_contribution, FALSE),
                           COALESCE(training_consent, FALSE),
                           stockmass_cm
                    FROM videos
                    WHERE status = 'done'
                """)
                for row in cur.fetchall():
                    (job_id, filename, horse_name, gait_label, camera_angle,
                     gait_detected, output_path, created_at, is_tc, tc, stockmass_cm) = row
                    db_job_ids.add(job_id)
                    if job_id in jobs:
                        continue
                    if not output_path or not Path(output_path).exists():
                        continue
                    jobs[job_id] = JobState(
                        job_id=job_id,
                        filename=filename or "",
                        horse_name=horse_name,
                        gait_label=gait_label,
                        camera_angle=camera_angle,
                        gait_detected=gait_detected,
                        input_path="",
                        output_path=output_path,
                        status="done",
                        progress=100,
                        message="Analyse abgeschlossen!",
                        created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
                        is_training_contribution=bool(is_tc),
                        training_consent=bool(tc),
                        stockmass_cm=stockmass_cm,
                    )
    except Exception:
        logger.exception("DB-Recovery fehlgeschlagen – Fallback auf Dateisystem")

    # ── 2. Fallback: Dateisystem für Videos ohne DB-Eintrag (Backward-Compat) ─
    for mp4 in OUTPUTS_DIR.glob("*.mp4"):
        # Nur echte finale MP4s (nicht *.mp4.tmp.mp4 o.ä.) – UUID ist der erste Namensteil
        job_id = mp4.name.split('.')[0]
        if not _UUID_RE.match(job_id):
            continue
        if job_id in jobs or job_id in db_job_ids:
            continue
        mtime = datetime.fromtimestamp(mp4.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
        job = JobState(
            job_id=job_id,
            input_path="",
            output_path=str(mp4),
            status="done",
            progress=100,
            message="Analyse abgeschlossen!",
            created_at=mtime,
        )
        jobs[job_id] = job
        # DB-Eintrag anlegen, damit Annotationen und korrektes Löschen funktionieren
        try:
            _upsert_video_sync(job, "done")
        except Exception:
            logger.exception("DB-Upsert für Recovery-Job %s fehlgeschlagen", mp4.stem)


def _upsert_video_sync(
    job: "JobState",
    db_status: str,
    gait_detected: str | None = None,
    camera_angle_detected: str | None = None,
) -> None:
    """Legt Video-Zeile an oder aktualisiert sie – sync psycopg3 für Thread-Kontext.
    camera_angle_detected wird nur gesetzt wenn der Nutzer keinen Winkel angegeben hat."""
    import psycopg  # type: ignore
    import psycopg.types.json  # type: ignore  # noqa: F401

    # Auto-erkannten Winkel nur verwenden wenn Nutzer keinen angegeben hat
    effective_angle = job.camera_angle or camera_angle_detected

    with psycopg.connect(_DB_URL_SYNC) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO videos (job_id, filename, horse_name, gait_label, camera_angle,
                                    status, gait_detected, progress, message, output_path, user_id,
                                    is_training_contribution, training_consent, stockmass_cm)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    gait_detected = EXCLUDED.gait_detected,
                    camera_angle = COALESCE(videos.camera_angle, EXCLUDED.camera_angle),
                    progress = EXCLUDED.progress,
                    message = EXCLUDED.message
                """,
                (
                    job.job_id,
                    job.filename,
                    job.horse_name,
                    job.gait_label,
                    effective_angle,
                    db_status,
                    gait_detected,
                    job.progress,
                    job.message,
                    job.output_path,
                    job.user_id,
                    job.is_training_contribution,
                    job.training_consent,
                    job.stockmass_cm,
                ),
            )
        conn.commit()


def _run_processing(job_id: str) -> None:
    with _lock:
        jobs[job_id].status = "processing"
        input_path = jobs[job_id].input_path
        output_path = jobs[job_id].output_path
        job_snapshot = jobs[job_id].model_copy()

    try:
        _upsert_video_sync(job_snapshot, "processing")
    except Exception:
        logger.exception("Video-DB-Insert fehlgeschlagen für job %s", job_id)

    def cb(pct: int, msg: str) -> None:
        with _lock:
            jobs[job_id].progress = pct
            jobs[job_id].message = msg

    try:
        with _lock:
            stockmass_cm = jobs[job_id].stockmass_cm
        detected_gait, detected_angle, speed_ms, output_fps = get_processor().process(
            input_path, output_path, cb, video_db_id=job_id, stockmass_cm=stockmass_cm
        )
        if UPLOAD_TTL_HOURS == 0:
            Path(input_path).unlink(missing_ok=True)
        with _lock:
            jobs[job_id].status = "done"
            jobs[job_id].progress = 100
            jobs[job_id].gait_detected = detected_gait
            jobs[job_id].speed_ms = speed_ms
            jobs[job_id].output_fps = output_fps
            if not jobs[job_id].camera_angle and detected_angle:
                jobs[job_id].camera_angle = detected_angle
            final_snapshot = jobs[job_id].model_copy()
        try:
            _upsert_video_sync(
                final_snapshot, "done",
                gait_detected=detected_gait,
                camera_angle_detected=detected_angle,
            )
        except Exception:
            logger.exception("Video-DB-Update (done) fehlgeschlagen für job %s", job_id)
    except Exception as exc:
        logger.exception("Verarbeitung fehlgeschlagen für job %s", job_id)
        err_snapshot = None
        with _lock:
            if job_id in jobs:
                jobs[job_id].status = "error"
                jobs[job_id].message = f"Fehler: {exc}"
                err_snapshot = jobs[job_id].model_copy()
        if err_snapshot:
            try:
                _upsert_video_sync(err_snapshot, "error")
            except Exception:
                logger.exception("Video-DB-Update (error) fehlgeschlagen für job %s", job_id)


def _cleanup_expired_outputs() -> None:
    """Löscht Output-Dateien, die älter als OUTPUT_TTL_HOURS sind; setzt Status auf 'expired'."""
    while True:
        time.sleep(3600)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # K4: Unter Lock nur IDs + Pfade sammeln und Status setzen; Dateien außerhalb löschen
        paths_to_delete: list[Path] = []
        with _lock:
            for job in jobs.values():
                if job.status not in ("done", "expired"):
                    continue
                age_hours = (now - job.created_at).total_seconds() / 3600
                if age_hours >= OUTPUT_TTL_HOURS:
                    output = Path(job.output_path)
                    if output.exists():
                        paths_to_delete.append(output)
                    job.status = "expired"
                    job.message = f"Ausgabedatei nach {OUTPUT_TTL_HOURS}h automatisch gelöscht."
        # Dateisystem-Operationen außerhalb des Locks ausführen
        for output in paths_to_delete:
            output.unlink(missing_ok=True)

        # Upload-Dateien bereinigen, wenn UPLOAD_TTL_HOURS > 0
        if UPLOAD_TTL_HOURS > 0:
            upload_paths: list[Path] = []
            with _lock:
                for job in jobs.values():
                    age_hours = (now - job.created_at).total_seconds() / 3600
                    if age_hours >= UPLOAD_TTL_HOURS and job.input_path:
                        p = Path(job.input_path)
                        if p.exists():
                            upload_paths.append(p)
                            job.input_path = ""
            for p in upload_paths:
                p.unlink(missing_ok=True)


threading.Thread(target=_cleanup_expired_outputs, daemon=True, name="ttl-cleanup").start()


@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    horse_name: Optional[str] = Form(None),
    gait_label: Optional[str] = Form(None),
    camera_angle: Optional[str] = Form(None),
    is_training_contribution: bool = Form(False),
    training_consent: bool = Form(False),
    stockmass_cm: Optional[int] = Form(None),
    current_user: Optional[User] = Depends(get_optional_user),
) -> UploadResponse:
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Format nicht unterstützt: {suffix}")

    gait_label = _normalize_gait(gait_label)
    camera_angle = _normalize_angle(camera_angle)

    if gait_label and gait_label not in ALLOWED_GAITS:
        raise HTTPException(400, f"Unbekannte Gangart: {gait_label}. Erlaubt: {', '.join(sorted(ALLOWED_GAITS))}")
    if camera_angle and camera_angle not in ALLOWED_ANGLES:
        raise HTTPException(400, f"Unbekannter Kamerawinkel: {camera_angle}. Erlaubt: {', '.join(sorted(ALLOWED_ANGLES))}")
    if is_training_contribution and not training_consent:
        raise HTTPException(422, "Lernfreigabe erfordert explizite Zustimmung.")
    if training_consent:
        is_training_contribution = True
    if stockmass_cm is not None and not (80 <= stockmass_cm <= 200):
        raise HTTPException(422, "Stockmaß muss zwischen 80 und 200 cm liegen.")

    job_id = str(uuid.uuid4())
    input_path = str(UPLOADS_DIR / f"{job_id}{suffix}")
    output_path = str(OUTPUTS_DIR / f"{job_id}.mp4")

    async with aiofiles.open(input_path, "wb") as fp:
        while chunk := await file.read(1024 * 1024):
            await fp.write(chunk)

    file_size_mb = Path(input_path).stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_UPLOAD_MB:
        Path(input_path).unlink(missing_ok=True)
        raise HTTPException(413, f"Datei zu groß. Maximum: {MAX_UPLOAD_MB} MB")

    with _lock:
        jobs[job_id] = JobState(
            job_id=job_id,
            input_path=input_path,
            output_path=output_path,
            filename=file.filename or "video",
            horse_name=horse_name,
            gait_label=gait_label,
            camera_angle=camera_angle,
            user_id=current_user.id if current_user else None,
            is_training_contribution=is_training_contribution,
            training_consent=training_consent,
            stockmass_cm=stockmass_cm,
        )

    background_tasks.add_task(
        lambda: threading.Thread(
            target=_run_processing, args=(job_id,), daemon=True
        ).start()
    )
    return UploadResponse(job_id=job_id, filename=file.filename or "video")


@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str) -> JobStatus:
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden.")
    return JobStatus(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        gait_detected=job.gait_detected,
        horse_name=job.horse_name,
        gait_label=job.gait_label,
        camera_angle=job.camera_angle,
        stockmass_cm=job.stockmass_cm,
        speed_ms=job.speed_ms,
        output_fps=job.output_fps,
    )


@app.get("/api/videos", response_model=List[VideoListItem])
async def list_videos(db: AsyncSession = Depends(get_db)) -> List[VideoListItem]:
    with _lock:
        snapshot = list(jobs.values())
    snapshot.sort(key=lambda j: j.created_at, reverse=True)

    # Annotierte Job-IDs in einer Batch-Abfrage ermitteln
    job_ids = [j.job_id for j in snapshot]
    annotated_ids: set[str] = set()
    if job_ids:
        try:
            ann_result = await db.execute(
                select(Frame.video_id).distinct()
                .join(Annotation, Annotation.frame_id == Frame.id)
                .where(Frame.video_id.in_(job_ids))
            )
            annotated_ids = {row[0] for row in ann_result}
        except Exception:
            logger.exception("Annotation-Count-Abfrage fehlgeschlagen")

    return [
        VideoListItem(
            job_id=j.job_id,
            filename=j.filename,
            horse_name=j.horse_name,
            gait_label=j.gait_label,
            camera_angle=j.camera_angle,
            status=j.status,
            gait_detected=j.gait_detected,
            progress=j.progress,
            message=j.message,
            created_at=j.created_at.isoformat(),
            is_training_contribution=j.is_training_contribution,
            training_consent=j.training_consent,
            is_annotated=j.job_id in annotated_ids,
            stockmass_cm=j.stockmass_cm,
            speed_ms=j.speed_ms,
            output_fps=j.output_fps,
        )
        for j in snapshot
    ]


@app.get("/api/download/{job_id}")
async def download_result(job_id: str) -> FileResponse:
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "Ergebnis nicht verfügbar.")
    if not Path(job.output_path).exists():
        raise HTTPException(404, "Ausgabedatei nicht gefunden.")
    return FileResponse(
        job.output_path,
        media_type="video/mp4",
        filename=f"toeltonaut_{job_id[:8]}.mp4",
    )


_HOOF_MAP = {
    "Nearfrontfetlock": "VL",
    "Offfrontfetlock":  "VR",
    "Nearhindfetlock":  "HL",
    "Offhindfetlock":   "HR",
}


@app.get("/api/takt-timeline/{job_id}", response_model=TaktTimelineResponse)
async def get_takt_timeline(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> TaktTimelineResponse:
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden.")
    if job.status not in ("done", "processing"):
        raise HTTPException(409, "Keypoints noch nicht verfügbar.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames = frames_result.scalars().all()

    if not frames:
        raise HTTPException(404, "Keine Frame-Daten in der Datenbank.")

    frame_ids = [f.id for f in frames]
    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id.in_(frame_ids))
    )
    kp_rows = kp_result.scalars().all()

    kp_by_frame: dict[int, list] = {}
    for kp in kp_rows:
        kp_by_frame.setdefault(kp.frame_id, []).extend(
            kp.data if isinstance(kp.data, list) else []
        )

    tracks: dict[str, list] = {"VL": [], "VR": [], "HL": [], "HR": []}

    for f in frames:
        kp_list = kp_by_frame.get(f.id, [])
        for entry in kp_list:
            leg = _HOOF_MAP.get(entry.get("name", ""))
            if leg is None:
                continue
            tracks[leg].append(TaktTrackPoint(frame=f.frame_nr, y_norm=entry["y"]))

    total_frames = max((f.frame_nr for f in frames), default=0) + 1

    if len(frames) >= 2:
        span_ms = (frames[-1].timestamp_ms or 0) - (frames[0].timestamp_ms or 0)
        fps = (len(frames) - 1) * 1000.0 / span_ms if span_ms > 0 else 25.0
    else:
        fps = 25.0

    non_sv = [f.frame_nr for f in frames if f.is_side_view is False]

    return TaktTimelineResponse(
        job_id=job_id,
        fps=round(fps, 2),
        total_frames=total_frames,
        tracks=tracks,
        non_side_view_frames=non_sv,
    )


@app.get("/api/gait-segments/{job_id}", response_model=List[GaitSegment])
async def get_gait_segments(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[GaitSegment]:
    """Gangarten-Segmente: zeitliche Abschnitte mit jeweils einer erkannten Gangart."""
    _require_job_id(job_id)
    frames_result = await db.execute(
        select(Frame.frame_nr, Frame.timestamp_ms, Frame.gait)
        .where(Frame.video_id == job_id, Frame.gait.isnot(None))
        .order_by(Frame.frame_nr)
    )
    rows = frames_result.all()

    if not rows:
        raise HTTPException(404, "Keine Gangarten-Daten verfügbar.")

    segments: list[GaitSegment] = []
    curr_gait = rows[0][2]
    curr_start_frame = rows[0][0]
    curr_start_ms = float(rows[0][1] or 0.0)
    curr_count = 1

    for frame_nr, timestamp_ms, gait in rows[1:]:
        if gait != curr_gait:
            segments.append(GaitSegment(
                gait=curr_gait,
                start_frame=curr_start_frame,
                end_frame=frame_nr - 1,
                start_ms=curr_start_ms,
                end_ms=float(timestamp_ms or 0.0),
                frame_count=curr_count,
            ))
            curr_gait = gait
            curr_start_frame = frame_nr
            curr_start_ms = float(timestamp_ms or 0.0)
            curr_count = 1
        else:
            curr_count += 1

    segments.append(GaitSegment(
        gait=curr_gait,
        start_frame=curr_start_frame,
        end_frame=rows[-1][0],
        start_ms=curr_start_ms,
        end_ms=float(rows[-1][1] or 0.0),
        frame_count=curr_count,
    ))
    return segments




@app.get("/api/toelt-score/{job_id}", response_model=ToltScoreResponse)
async def get_toelt_score(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ToltScoreResponse:
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames = frames_result.scalars().all()

    if not frames:
        raise HTTPException(404, "Keine Frame-Daten in der Datenbank.")

    frame_ids = [f.id for f in frames]
    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id.in_(frame_ids))
    )
    kp_by_frame: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame.setdefault(kp.frame_id, []).extend(
            kp.data if isinstance(kp.data, list) else []
        )

    tracks: dict[str, list] = {"VL": [], "VR": [], "HL": [], "HR": []}
    for f in frames:
        for entry in kp_by_frame.get(f.id, []):
            leg = _HOOF_MAP.get(entry.get("name", ""))
            if leg:
                tracks[leg].append(TaktTrackPoint(frame=f.frame_nr, y_norm=entry["y"]))

    span_ms = (frames[-1].timestamp_ms or 0) - (frames[0].timestamp_ms or 0) if len(frames) >= 2 else 0
    fps = (len(frames) - 1) * 1000.0 / span_ms if span_ms > 0 else 25.0

    result = ToltScorer().score(tracks, fps=fps)
    return ToltScoreResponse(
        job_id=job_id,
        score=result.score,
        feif_grade=result.feif_grade,
        errors=[
            ToltErrorModel(
                type=e.type,
                severity=e.severity,
                frame_range=list(e.frame_range),
                description=e.description,
            )
            for e in result.errors
        ],
        takt_regularity=result.takt_regularity,
        beat_count=len(result.beat_intervals),
        disclaimer=result.disclaimer,
        lap=result.lap,
        df=result.df,
        subclassification=result.subclassification,
    )


@app.get("/api/rennpass-score/{job_id}", response_model=RennpassScoreResponse)
async def get_rennpass_score(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> RennpassScoreResponse:
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames = frames_result.scalars().all()

    if not frames:
        raise HTTPException(404, "Keine Frame-Daten in der Datenbank.")

    frame_ids = [f.id for f in frames]
    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id.in_(frame_ids))
    )
    kp_by_frame: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame.setdefault(kp.frame_id, []).extend(
            kp.data if isinstance(kp.data, list) else []
        )

    tracks: dict[str, list] = {"VL": [], "VR": [], "HL": [], "HR": []}
    for f in frames:
        for entry in kp_by_frame.get(f.id, []):
            leg = _HOOF_MAP.get(entry.get("name", ""))
            if leg:
                tracks[leg].append(TaktTrackPoint(frame=f.frame_nr, y_norm=entry["y"]))

    span_ms = (frames[-1].timestamp_ms or 0) - (frames[0].timestamp_ms or 0) if len(frames) >= 2 else 0
    fps = (len(frames) - 1) * 1000.0 / span_ms if span_ms > 0 else 25.0

    result = RennpassScorer().score(tracks, fps=fps)
    return RennpassScoreResponse(
        job_id=job_id,
        score=result.score,
        feif_grade=result.feif_grade,
        errors=[
            RennpassErrorModel(
                type=e.type,
                severity=e.severity,
                frame_range=list(e.frame_range),
                description=e.description,
            )
            for e in result.errors
        ],
        lateral_sync=result.lateral_sync,
        suspension_detected=result.suspension_detected,
        stride_count=result.stride_count,
        disclaimer=result.disclaimer,
    )


@app.post("/api/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if len(body.password) < 8:
        raise HTTPException(422, "Passwort muss mindestens 8 Zeichen lang sein.")
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(409, "E-Mail-Adresse bereits vergeben.")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == form.username, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-Mail oder Passwort falsch.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@app.get("/api/auth/me", response_model=UserMe)
async def me(current_user: User = Depends(get_current_user)) -> UserMe:
    return UserMe(id=current_user.id, email=current_user.email, created_at=current_user.created_at)


@app.delete("/api/auth/account")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """DSGVO-konforme Account-Löschung: Videos, Frames, Keypoints (CASCADE), Output-Dateien, Jobs-Dict, User."""
    # 1. Alle Videos des Users aus DB laden (für Disk-Cleanup)
    videos_result = await db.execute(
        select(Video).where(Video.user_id == current_user.id)
    )
    user_videos = videos_result.scalars().all()

    # 2. Output-Dateien von Disk löschen
    for video in user_videos:
        if video.output_path:
            Path(video.output_path).unlink(missing_ok=True)

    # 3. In-Memory Jobs bereinigen (Upload-Dateien + Jobs-Dict)
    job_ids_to_remove = [v.job_id for v in user_videos]
    with _lock:
        for jid in job_ids_to_remove:
            job = jobs.pop(jid, None)
            if job and job.input_path:
                Path(job.input_path).unlink(missing_ok=True)

    # 4. Videos aus DB per Bulk-Delete (Frames + Keypoints + Annotations per CASCADE)
    await db.execute(delete(Video).where(Video.user_id == current_user.id))

    # 5. User selbst löschen
    user_email = current_user.email
    await db.delete(current_user)
    await db.commit()

    return {"deleted": user_email}


@app.delete("/api/job/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_job_id(job_id)
    with _lock:
        job = jobs.pop(job_id, None)

    # Dateien löschen (nur wenn In-Memory-Job bekannt)
    if job:
        p_in = Path(job.input_path) if job.input_path else None
        if p_in and p_in.is_file():
            p_in.unlink(missing_ok=True)
        p_out = Path(job.output_path) if job.output_path else None
        if p_out and p_out.is_file():
            p_out.unlink(missing_ok=True)
    else:
        # Fallback: Output-Datei anhand bekannter Pfade suchen und löschen
        for p in OUTPUTS_DIR.glob(f"{job_id}.*"):
            p.unlink(missing_ok=True)
        for p in UPLOADS_DIR.glob(f"{job_id}.*"):
            p.unlink(missing_ok=True)

    # DB-Eintrag prüfen und löschen – CASCADE entfernt frames/keypoints/annotations
    result = await db.execute(delete(Video).where(Video.job_id == job_id))
    await db.commit()

    if not job and result.rowcount == 0:
        raise HTTPException(404, "Job nicht gefunden.")

    return {"deleted": job_id}


@app.patch("/api/job/{job_id}/metadata", response_model=dict)
async def update_job_metadata(
    job_id: str,
    body: VideoMetadataUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden.")

    # Validate
    if body.gait_label is not None and body.gait_label != "" and body.gait_label not in ALLOWED_GAITS:
        raise HTTPException(400, f"Unbekannte Gangart: {body.gait_label}")
    if body.camera_angle is not None and body.camera_angle != "" and body.camera_angle not in ALLOWED_ANGLES:
        raise HTTPException(400, f"Unbekannte Kameraposition: {body.camera_angle}")

    # Build update dict – only fields that are explicitly set (not None)
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if values:
        await db.execute(
            update(Video)
            .where(Video.job_id == job_id)
            .values(**values)
        )
        await db.commit()

    # Update in-memory job state
    with _lock:
        if body.horse_name is not None:
            job.horse_name = body.horse_name
        if body.gait_label is not None:
            job.gait_label = body.gait_label
        if body.camera_angle is not None:
            job.camera_angle = body.camera_angle
        if body.training_consent is not None:
            job.training_consent = body.training_consent
            if body.training_consent:
                job.is_training_contribution = True

    return {"updated": job_id}


_COCO_KEYPOINT_NAMES = [
    "Nose", "Eye",
    "Nearknee", "Nearfrontfetlock", "Nearfrontfoot",
    "Offknee", "Offfrontfetlock", "Offfrontfoot",
    "Shoulder", "Midshoulder", "Elbow", "Girth", "Wither",
    "Nearhindhock", "Nearhindfetlock", "Nearhindfoot",
    "Hip", "Stifle",
    "Offhindhock", "Offhindfetlock", "Offhindfoot",
    "Ischium",
]

# Horse-10 COCO skeleton: 0-based index pairs
_HORSE10_SKELETON: list[list[int]] = [
    [0, 1],   # Nose → Eye
    [0, 8],   # Nose → Shoulder
    [8, 9],   # Shoulder → Midshoulder
    [9, 10],  # Midshoulder → Elbow
    [8, 12],  # Shoulder → Wither
    [12, 11], # Wither → Girth
    [12, 16], # Wither → Hip
    [16, 21], # Hip → Ischium
    [16, 17], # Hip → Stifle
    [17, 13], # Stifle → Nearhindhock
    [13, 14], # Nearhindhock → Nearhindfetlock
    [14, 15], # Nearhindfetlock → Nearhindfoot
    [17, 18], # Stifle → Offhindhock
    [18, 19], # Offhindhock → Offhindfetlock
    [19, 20], # Offhindfetlock → Offhindfoot
    [10, 2],  # Elbow → Nearknee
    [2, 3],   # Nearknee → Nearfrontfetlock
    [3, 4],   # Nearfrontfetlock → Nearfrontfoot
    [10, 5],  # Elbow → Offknee
    [5, 6],   # Offknee → Offfrontfetlock
    [6, 7],   # Offfrontfetlock → Offfrontfoot
]


def _build_coco_zip(
    job_id: str,
    output_path: str,
    frames: list[dict],        # [{"id": int, "frame_nr": int, "timestamp_ms": float|None}]
    ann_by_frame: dict,        # {frame_id: [kp_entries]}
    kp_by_frame: dict,         # {frame_id: [kp_entries]}
) -> bytes:
    """CPU-bound: builds in-memory ZIP with coco.json + images/. Returns raw bytes."""
    import cv2  # type: ignore
    import numpy  # type: ignore

    cap = cv2.VideoCapture(output_path)
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    fps_cap = cap.get(cv2.CAP_PROP_FPS) or 25.0

    coco_images = []
    coco_annotations = []
    ann_id = 1
    image_jpegs: dict[str, bytes] = {}

    for f in frames:
        frame_id = f["id"]
        frame_nr = f["frame_nr"]
        ts_ms = f["timestamp_ms"]

        kp_list = ann_by_frame.get(frame_id) or kp_by_frame.get(frame_id, [])
        if not kp_list:
            continue

        img_filename = f"images/frame_{frame_nr:06d}.jpg"

        seek_ms = ts_ms if ts_ms is not None else frame_nr * 1000.0 / fps_cap
        cap.set(cv2.CAP_PROP_POS_MSEC, seek_ms)
        ret, frame_img = cap.read()
        if ret and frame_img is not None:
            ok, buf = cv2.imencode(".jpg", frame_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ok:
                image_jpegs[img_filename] = buf.tobytes()
        else:
            blank = numpy.zeros((vid_h, vid_w, 3), dtype=numpy.uint8)
            _, buf = cv2.imencode(".jpg", blank, [cv2.IMWRITE_JPEG_QUALITY, 90])
            image_jpegs[img_filename] = buf.tobytes()

        coco_images.append({"id": frame_nr, "file_name": img_filename, "width": vid_w, "height": vid_h})

        kp_name_map = {e["name"]: e for e in kp_list if "name" in e}
        flat_kps: list[float] = []
        num_kps = 0

        for kp_name in _COCO_KEYPOINT_NAMES:
            e = kp_name_map.get(kp_name)
            if e and float(e.get("confidence", 0)) > 0:
                px = float(e["x"]) * vid_w
                py = float(e["y"]) * vid_h
                flat_kps.extend([px, py, 2])
                num_kps += 1
            else:
                flat_kps.extend([0.0, 0.0, 0])

        if num_kps == 0:
            coco_images.pop()
            continue

        xs = [flat_kps[i * 3] for i in range(len(_COCO_KEYPOINT_NAMES)) if flat_kps[i * 3 + 2] == 2]
        ys = [flat_kps[i * 3 + 1] for i in range(len(_COCO_KEYPOINT_NAMES)) if flat_kps[i * 3 + 2] == 2]
        pad = 20.0
        bx = max(0.0, min(xs) - pad)
        by = max(0.0, min(ys) - pad)
        bw = min(float(vid_w) - bx, max(xs) - min(xs) + 2 * pad)
        bh = min(float(vid_h) - by, max(ys) - min(ys) + 2 * pad)

        coco_annotations.append({
            "id": ann_id,
            "image_id": frame_nr,
            "category_id": 1,
            "keypoints": flat_kps,
            "num_keypoints": num_kps,
            "bbox": [bx, by, bw, bh],
            "area": bw * bh,
            "iscrowd": 0,
        })
        ann_id += 1

    cap.release()

    from datetime import datetime, timezone as _tz
    coco_doc = {
        "info": {
            "version": "1.0",
            "description": "Töltonaut MMPose Export",
            "job_id": job_id,
            "date_created": datetime.now(_tz.utc).isoformat(),
        },
        "licenses": [],
        "categories": [{
            "id": 1,
            "name": "horse",
            "supercategory": "animal",
            "keypoints": _COCO_KEYPOINT_NAMES,
            "skeleton": _HORSE10_SKELETON,
        }],
        "images": coco_images,
        "annotations": coco_annotations,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("coco.json", json.dumps(coco_doc, ensure_ascii=False, indent=2))
        for img_path, img_bytes in image_jpegs.items():
            zf.writestr(img_path, img_bytes)
    return buf.getvalue()


@app.get("/api/training/export/{job_id}")
async def export_coco(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Exportiert Keypoints als COCO-JSON für das MMPose-Training.
    Nur für Videos mit is_training_contribution=True und training_consent=True."""
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(404, "Job nicht gefunden.")
    if not job.is_training_contribution or not job.training_consent:
        raise HTTPException(403, "Export nur für Videos mit Lernfreigabe erlaubt.")
    if job.status not in ("done",):
        raise HTTPException(409, "Keypoints noch nicht verfügbar – bitte warten, bis die Verarbeitung abgeschlossen ist.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames = frames_result.scalars().all()

    if not frames:
        raise HTTPException(404, "Keine Frame-Daten in der Datenbank.")

    # Echte Video-Dimensionen ermitteln
    _vid_w, _vid_h = 1920, 1080
    if job.output_path and Path(job.output_path).exists():
        _cap = cv2.VideoCapture(job.output_path)
        if _cap.isOpened():
            _vid_w = int(_cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
            _vid_h = int(_cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        _cap.release()

    frame_ids = [f.id for f in frames]
    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id.in_(frame_ids))
    )
    kp_rows = kp_result.scalars().all()

    kp_by_frame: dict[int, list] = {}
    for kp in kp_rows:
        kp_by_frame.setdefault(kp.frame_id, []).extend(
            kp.data if isinstance(kp.data, list) else []
        )

    frame_by_id = {f.id: f for f in frames}

    coco_images = []
    coco_annotations = []
    ann_id = 1

    for f in frames:
        coco_images.append({
            "id": f.frame_nr,
            "file_name": f"frame_{f.frame_nr:06d}.jpg",
            "width": _vid_w,
            "height": _vid_h,
        })

        kp_list = kp_by_frame.get(f.id, [])
        if not kp_list:
            continue

        kp_name_map = {entry["name"]: entry for entry in kp_list if "name" in entry}

        flat_kps: list[float] = []
        num_kps = 0
        for kp_name in _COCO_KEYPOINT_NAMES:
            entry = kp_name_map.get(kp_name)
            if entry:
                x = float(entry.get("x", 0)) * _vid_w
                y = float(entry.get("y", 0)) * _vid_h
                v = 2  # sichtbar
                num_kps += 1
            else:
                x, y, v = 0.0, 0.0, 0  # nicht annotiert
            flat_kps.extend([x, y, v])

        if num_kps == 0:
            continue

        coco_annotations.append({
            "id": ann_id,
            "image_id": f.frame_nr,
            "category_id": 1,
            "keypoints": flat_kps,
            "num_keypoints": num_kps,
        })
        ann_id += 1

    coco_doc = {
        "info": {
            "version": "1.0",
            "description": "Töltonaut Training Export",
            "gait_label": job.gait_label,
            "job_id": job_id,
        },
        "categories": [
            {
                "id": 1,
                "name": "horse",
                "supercategory": "animal",
                "keypoints": _COCO_KEYPOINT_NAMES,
                "skeleton": [],
            }
        ],
        "images": coco_images,
        "annotations": coco_annotations,
    }

    return Response(
        content=json.dumps(coco_doc, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="toeltonaut_coco_{job_id[:8]}.json"'},
    )


@app.get("/api/stats", response_model=AppStats)
async def get_stats() -> AppStats:
    with _lock:
        snapshot = list(jobs.values())

    total_videos = len(snapshot)
    done_videos = sum(1 for j in snapshot if j.status == "done")
    training_contributions = sum(1 for j in snapshot if j.is_training_contribution and j.training_consent)

    gait_distribution: dict[str, int] = {}
    for j in snapshot:
        gait = j.gait_detected or j.gait_label
        if gait:
            gait_distribution[gait] = gait_distribution.get(gait, 0) + 1

    return AppStats(
        total_videos=total_videos,
        done_videos=done_videos,
        training_contributions=training_contributions,
        gait_distribution=gait_distribution,
        avg_toelt_score=None,
    )


@app.get("/api/learning-status", response_model=LearningStatus)
async def get_learning_status(db: AsyncSession = Depends(get_db)) -> LearningStatus:
    """Übersicht über den Lern-Loop: Frames, Annotationen, Modellversion."""
    from .ai_config import get_ai_config
    cfg = get_ai_config()

    total_videos = (await db.execute(select(func.count()).select_from(Video))).scalar_one()
    training_videos = (await db.execute(
        select(func.count()).select_from(Video)
        .where(Video.training_consent == True)
    )).scalar_one()
    total_frames = (await db.execute(select(func.count()).select_from(Frame))).scalar_one()
    annotated_frames = (await db.execute(
        select(func.count()).select_from(Annotation)
    )).scalar_one()

    gait_rows = (await db.execute(
        select(Video.gait_detected, func.count(Video.job_id))
        .where(Video.gait_detected.isnot(None))
        .group_by(Video.gait_detected)
    )).all()
    gait_distribution = {row[0]: row[1] for row in gait_rows}

    return LearningStatus(
        model_version=cfg.model_version,
        total_videos=total_videos,
        training_videos=training_videos,
        total_frames=total_frames,
        annotated_frames=annotated_frames,
        gait_distribution=gait_distribution,
    )


@app.get("/api/export/{job_id}")
async def export_job_keypoints(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportiert alle Keypoints + Annotationen eines Videos als COCO JSON.
    Keine Lernfreigabe-Pflicht – für alle abgeschlossenen Videos."""
    import cv2  # type: ignore
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "Job nicht gefunden oder noch nicht abgeschlossen.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames = frames_result.scalars().all()
    if not frames:
        raise HTTPException(404, "Keine Frame-Daten verfügbar.")

    # Echte Video-Dimensionen
    _vid_w, _vid_h = 1920, 1080
    if job.output_path and Path(job.output_path).exists():
        _cap = cv2.VideoCapture(job.output_path)
        if _cap.isOpened():
            _vid_w = int(_cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
            _vid_h = int(_cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        _cap.release()

    frame_ids = [f.id for f in frames]

    # Annotations haben Vorrang
    ann_result = await db.execute(
        select(Annotation).where(Annotation.frame_id.in_(frame_ids))
    )
    ann_by_frame: dict[int, list] = {}
    for ann in ann_result.scalars().all():
        kps = ann.keypoints if isinstance(ann.keypoints, list) else []
        ann_by_frame[ann.frame_id] = kps

    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id.in_(frame_ids))
    )
    kp_by_frame: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame[kp.frame_id] = kp.data if isinstance(kp.data, list) else []

    coco_images = []
    coco_annotations = []
    ann_id = 1

    for f in frames:
        kp_list = ann_by_frame.get(f.id) or kp_by_frame.get(f.id, [])
        if not kp_list:
            continue
        coco_images.append({
            "id": f.frame_nr,
            "file_name": f"frame_{f.frame_nr:06d}.jpg",
            "width": _vid_w,
            "height": _vid_h,
            "gait": f.gait,
            "timestamp_ms": f.timestamp_ms,
        })
        kp_name_map = {e["name"]: e for e in kp_list if "name" in e}
        flat_kps: list[float] = []
        num_kps = 0
        kp_names_used = list(kp_name_map.keys())
        for kp_name in kp_names_used:
            e = kp_name_map[kp_name]
            flat_kps.extend([
                float(e.get("x", 0)) * _vid_w,
                float(e.get("y", 0)) * _vid_h,
                2,
            ])
            num_kps += 1
        coco_annotations.append({
            "id": ann_id,
            "image_id": f.frame_nr,
            "category_id": 1,
            "keypoints": flat_kps,
            "num_keypoints": num_kps,
            "is_manual": f.id in ann_by_frame,
        })
        ann_id += 1

    kp_names_all = sorted({
        e["name"]
        for f_id in list(ann_by_frame.keys()) + list(kp_by_frame.keys())
        for e in (ann_by_frame.get(f_id) or kp_by_frame.get(f_id, []))
        if "name" in e
    })

    coco_doc = {
        "info": {"version": "1.0", "description": "Töltonaut Export", "job_id": job_id,
                 "horse_name": job.horse_name, "gait_label": job.gait_label},
        "categories": [{"id": 1, "name": "horse", "supercategory": "animal",
                        "keypoints": kp_names_all, "skeleton": []}],
        "images": coco_images,
        "annotations": coco_annotations,
    }
    return Response(
        content=json.dumps(coco_doc, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="toeltonaut_export_{job_id[:8]}.json"'},
    )


@app.get("/api/export-coco/{job_id}")
async def export_coco_zip(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """COCO ZIP export: coco.json + extracted frame images for MMPose fine-tuning."""
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "Job nicht gefunden oder noch nicht abgeschlossen.")
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(404, "Ausgabedatei nicht gefunden.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames_orm = list(frames_result.scalars().all())
    if not frames_orm:
        raise HTTPException(404, "Keine Frame-Daten verfügbar.")

    frame_ids = [f.id for f in frames_orm]

    ann_result = await db.execute(select(Annotation).where(Annotation.frame_id.in_(frame_ids)))
    ann_by_frame: dict[int, list] = {
        ann.frame_id: (ann.keypoints if isinstance(ann.keypoints, list) else [])
        for ann in ann_result.scalars().all()
    }

    kp_result = await db.execute(select(Keypoint).where(Keypoint.frame_id.in_(frame_ids)))
    kp_by_frame: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame.setdefault(kp.frame_id, [])
        if isinstance(kp.data, list):
            kp_by_frame[kp.frame_id].extend(kp.data)

    # Convert ORM objects to plain dicts before executor call
    frames_plain = [{"id": f.id, "frame_nr": f.frame_nr, "timestamp_ms": f.timestamp_ms} for f in frames_orm]

    loop = asyncio.get_running_loop()
    zip_bytes = await loop.run_in_executor(
        None, _build_coco_zip, job_id, job.output_path, frames_plain, ann_by_frame, kp_by_frame
    )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="toeltonaut_coco_{job_id[:8]}.zip"'},
    )


@app.get("/api/metrics/{job_id}")
async def export_metrics_csv(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Metriken-CSV-Export: frame_nr, timestamp_ms, gait, is_side_view pro Frame."""
    _require_job_id(job_id)
    rows_result = await db.execute(
        select(Frame.frame_nr, Frame.timestamp_ms, Frame.gait, Frame.is_side_view)
        .where(Frame.video_id == job_id)
        .order_by(Frame.frame_nr)
    )
    rows = rows_result.all()
    if not rows:
        raise HTTPException(404, "Keine Frame-Daten verfügbar.")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["frame_nr", "timestamp_ms", "gait", "is_side_view"])
    for frame_nr, timestamp_ms, gait, is_side_view in rows:
        if is_side_view is None:
            sv_str = ""
        else:
            sv_str = "true" if is_side_view else "false"
        writer.writerow([frame_nr, timestamp_ms, gait or "", sv_str])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="metrics_{job_id[:8]}.csv"'},
    )


@app.post("/api/job/{job_id}/reanalyse")
async def reanalyse_job(
    job_id: str,
    body: dict = Body({}),
    background_tasks: BackgroundTasks = ...,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Neuanalyse in zwei Modi:
    - mode='gait-only' (Standard): Gangart-Erkennung auf gespeicherten Keypoints. ~2 Sek.
    - mode='full': Video komplett neu verarbeiten (YOLOv8 + MMPose). Dauert Minuten."""
    import cv2 as _cv2  # type: ignore
    from collections import Counter as _Counter
    from .mmpose_estimator import MMPosePoseEstimator
    from .gait_detector import GaitDetector

    mode = body.get("mode", "gait-only")
    _require_job_id(job_id)
    with _lock:
        job = jobs.get(job_id)
    if not job or job.status not in ("done", "expired"):
        raise HTTPException(404, "Job nicht gefunden oder noch nicht abgeschlossen.")

    # ── Vollständige Neuanalyse ─────────────────────────────────────────────
    if mode == "full":
        import shutil as _shutil
        if not job.output_path or not Path(job.output_path).exists():
            raise HTTPException(
                404,
                "Ausgabedatei nicht mehr verfügbar – bitte Video neu hochladen.",
            )
        # Ausgabe-MP4 als temporäre Eingabe kopieren (Input und Output wären sonst identisch)
        tmp_input = str(UPLOADS_DIR / f"{job_id}_reanalyse.mp4")
        _shutil.copy2(job.output_path, tmp_input)

        # Alte Frame-/Keypoint-Daten löschen (werden beim neuen Durchlauf neu angelegt)
        frame_ids_res = await db.execute(select(Frame.id).where(Frame.video_id == job_id))
        frame_ids = [r[0] for r in frame_ids_res.all()]
        if frame_ids:
            await db.execute(delete(Keypoint).where(Keypoint.frame_id.in_(frame_ids)))
            await db.execute(delete(Frame).where(Frame.id.in_(frame_ids)))
            await db.commit()

        with _lock:
            jobs[job_id].status = "queued"
            jobs[job_id].progress = 0
            jobs[job_id].message = "Vollständige Neuanalyse läuft…"
            jobs[job_id].input_path = tmp_input

        background_tasks.add_task(
            lambda: threading.Thread(target=_run_processing, args=(job_id,), daemon=True).start()
        )
        return {"job_id": job_id, "mode": "full", "status": "queued"}

    # ── Schnelle Neuanalyse (nur Gangart auf gespeicherten Keypoints) ───────
    if job.status != "done":
        raise HTTPException(404, "Job nicht gefunden oder noch nicht abgeschlossen.")

    frames_result = await db.execute(
        select(Frame).where(Frame.video_id == job_id).order_by(Frame.frame_nr)
    )
    frames = frames_result.scalars().all()
    if not frames:
        raise HTTPException(404, "Keine Frame-Daten in der Datenbank.")

    frame_ids = [f.id for f in frames]
    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id.in_(frame_ids))
    )
    kp_by_frame_id: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame_id.setdefault(kp.frame_id, []).extend(
            kp.data if isinstance(kp.data, list) else []
        )

    # Video-Dimensionen (für normiert→Pixel)
    vid_w, vid_h = 1920, 1080
    if job.output_path and Path(job.output_path).exists():
        _cap = _cv2.VideoCapture(job.output_path)
        if _cap.isOpened():
            vid_w = int(_cap.get(_cv2.CAP_PROP_FRAME_WIDTH)) or 1920
            vid_h = int(_cap.get(_cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        _cap.release()

    kp_name_to_idx = {name: i for i, name in enumerate(_COCO_KEYPOINT_NAMES)}

    if len(frames) >= 2:
        span_ms = (frames[-1].timestamp_ms or 0) - (frames[0].timestamp_ms or 0)
        fps = (len(frames) - 1) * 1000.0 / span_ms if span_ms > 0 else 25.0
    else:
        fps = 25.0

    # Alle Frames sind bereits stride-gefiltert → vid_stride=1 für GaitDetector
    detector = GaitDetector(fps=fps, vid_stride=1, fetlock_indices=MMPosePoseEstimator.FETLOCK_INDICES)

    _DEBOUNCE = 10
    current_gait: str | None = None
    pending_gait: str | None = None
    pending_count = 0
    frame_gaits: dict[int, str | None] = {}

    for frame in frames:
        kp_list = kp_by_frame_id.get(frame.id, [])
        is_sv = frame.is_side_view if frame.is_side_view is not None else True

        # Normierte Named-KPs → indizierte Pixel-Tupel (bbox = ganzer Frame)
        kp_name_map = {e["name"]: e for e in kp_list if isinstance(e, dict) and "name" in e}
        indexed: list[tuple[int, int]] = [(0, 0)] * len(_COCO_KEYPOINT_NAMES)
        for name, idx in kp_name_to_idx.items():
            e = kp_name_map.get(name)
            if e:
                indexed[idx] = (int(float(e.get("x", 0)) * vid_w), int(float(e.get("y", 0)) * vid_h))

        detector.update(indexed, (0, 0, vid_w, vid_h), is_side_view=is_sv)
        result = detector.detect()

        if result.name != "---":
            if result.name == pending_gait:
                pending_count += 1
            else:
                pending_gait = result.name
                pending_count = 1
            if pending_count >= _DEBOUNCE and pending_gait != current_gait:
                current_gait = pending_gait

        frame_gaits[frame.id] = current_gait

    # Frames in DB aktualisieren
    updated = 0
    for frame in frames:
        new_gait = frame_gaits.get(frame.id)
        if new_gait != frame.gait:
            frame.gait = new_gait
            updated += 1
    if updated:
        await db.commit()

    # Dominant-Gangart auf Video aktualisieren
    gait_counts = _Counter(g for g in frame_gaits.values() if g)
    dominant = gait_counts.most_common(1)[0][0] if gait_counts else None
    if dominant != job.gait_detected:
        await db.execute(update(Video).where(Video.job_id == job_id).values(gait_detected=dominant))
        await db.commit()
        with _lock:
            job.gait_detected = dominant

    return {
        "job_id": job_id,
        "updated_frames": updated,
        "total_frames": len(frames),
        "dominant_gait": dominant,
    }


@app.delete("/api/annotations/{job_id}")
async def reset_annotations(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Löscht alle manuellen Annotationen für ein Video (Keypoints aus ML-Analyse bleiben)."""
    _require_job_id(job_id)
    frame_ids_result = await db.execute(
        select(Frame.id).where(Frame.video_id == job_id)
    )
    frame_ids = [r[0] for r in frame_ids_result.all()]
    if not frame_ids:
        return {"deleted": 0}
    result = await db.execute(
        delete(Annotation).where(Annotation.frame_id.in_(frame_ids))
    )
    await db.commit()
    return {"deleted": result.rowcount}


@app.get("/api/training/jobs", response_model=List[TrainingJobItem])
async def list_training_jobs(db: AsyncSession = Depends(get_db)) -> List[TrainingJobItem]:
    result = await db.execute(select(TrainingJob).order_by(TrainingJob.created_at.desc()))
    rows = result.scalars().all()
    return [
        TrainingJobItem(
            id=row.id,
            model_version=row.model_version,
            mlflow_run_id=row.mlflow_run_id,
            metrics=row.metrics,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


@app.post("/api/training/jobs", response_model=TrainingJobItem, status_code=201)
async def create_training_job(
    body: CreateTrainingJobRequest,
    db: AsyncSession = Depends(get_db),
) -> TrainingJobItem:
    job = TrainingJob(
        model_version=body.model_version,
        dataset_snapshot=body.dataset_snapshot,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return TrainingJobItem(
        id=job.id,
        model_version=job.model_version,
        mlflow_run_id=job.mlflow_run_id,
        metrics=job.metrics,
        created_at=job.created_at.isoformat(),
    )


@app.get("/api/frame/{job_id}/{frame_nr}")
async def get_frame(job_id: str, frame_nr: int) -> Response:
    """Extrahiert einen Frame aus dem Output-Video und gibt ihn als JPEG zurück."""
    _require_job_id(job_id)
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    with _lock:
        job = jobs.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "Job nicht gefunden oder noch nicht abgeschlossen.")

    output_path = job.output_path
    if not Path(output_path).exists():
        raise HTTPException(404, "Ausgabedatei nicht gefunden.")

    cap = cv2.VideoCapture(output_path)
    if not cap.isOpened():
        raise HTTPException(500, "Video konnte nicht geöffnet werden.")
    total_output_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # frame_nr ist die Original-Framenummer (wie in der DB gespeichert).
    # Das Output-Video hat nur jeden VID_STRIDE-ten Frame → umrechnen.
    output_pos = frame_nr // VID_STRIDE
    if frame_nr < 0 or output_pos >= total_output_frames:
        cap.release()
        raise HTTPException(416, f"Frame {frame_nr} außerhalb des gültigen Bereichs.")

    cap.set(cv2.CAP_PROP_POS_FRAMES, output_pos)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(500, "Frame konnte nicht gelesen werden.")

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, "JPEG-Encoding fehlgeschlagen.")

    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.get("/api/keypoints/{job_id}/{frame_nr}", response_model=FrameKeypoints)
async def get_frame_keypoints(
    job_id: str,
    frame_nr: int,
    ms: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
) -> FrameKeypoints:
    """Sucht den nächstgelegenen Frame (timestamp_ms oder frame_nr). Annotations haben Vorrang."""
    _require_job_id(job_id)
    if ms is not None:
        frame_result = await db.execute(
            select(Frame)
            .where(Frame.video_id == job_id, Frame.timestamp_ms.is_not(None))
            .order_by(func.abs(Frame.timestamp_ms - ms))
            .limit(1)
        )
    else:
        frame_result = await db.execute(
            select(Frame)
            .where(Frame.video_id == job_id)
            .order_by(func.abs(Frame.frame_nr - frame_nr))
            .limit(1)
        )
    frame_row = frame_result.scalar_one_or_none()
    if frame_row is None:
        return FrameKeypoints(keypoints=[])

    frame_gait = frame_row.gait

    # Nicht-auswertbare Frames (Pferd zu weit weg / verdeckt / kein Seitenprofil):
    # Gangart-Label zurückgeben (für Timeline), aber keine Keypoints anzeigen.
    if frame_row.is_side_view is False:
        return FrameKeypoints(keypoints=[], gait=frame_gait)

    # Annotations (manuell korrigiert) haben Vorrang
    ann_result = await db.execute(
        select(Annotation).where(Annotation.frame_id == frame_row.id)
    )
    ann_row = ann_result.scalar_one_or_none()
    if ann_row:
        data = ann_row.keypoints if isinstance(ann_row.keypoints, list) else []
        return FrameKeypoints(keypoints=[
            KeypointEntry(name=e["name"], x=float(e.get("x", 0)),
                          y=float(e.get("y", 0)), confidence=float(e.get("confidence", 2.0)))
            for e in data if isinstance(e, dict) and "name" in e
        ], gait=frame_gait)

    # Fallback: ML-Keypoints
    kp_result = await db.execute(
        select(Keypoint).where(Keypoint.frame_id == frame_row.id)
    )
    keypoints: list[KeypointEntry] = []
    for kp in kp_result.scalars().all():
        data = kp.data if isinstance(kp.data, list) else []
        for entry in data:
            if isinstance(entry, dict) and "name" in entry:
                keypoints.append(KeypointEntry(
                    name=entry["name"], x=float(entry.get("x", 0)),
                    y=float(entry.get("y", 0)), confidence=float(entry.get("confidence", 0)),
                ))
    return FrameKeypoints(keypoints=keypoints, gait=frame_gait)


@app.post("/api/annotations/{job_id}/{frame_nr}")
async def save_annotation(
    job_id: str,
    frame_nr: int,
    body: FrameKeypoints,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Speichert manuell korrigierte Keypoints in der annotations-Tabelle."""
    _require_job_id(job_id)
    # Frame anlegen falls noch nicht vorhanden (z.B. bei Videos ohne DB-Frames)
    frame_result = await db.execute(
        select(Frame)
        .where(Frame.video_id == job_id, Frame.frame_nr == frame_nr)
    )
    frame_row = frame_result.scalar_one_or_none()

    if frame_row is None:
        with _lock:
            job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job nicht gefunden.")
        # Video-Eintrag sicherstellen (fehlt bei rein per-Dateisystem wiederhergestellten Jobs)
        video_result = await db.execute(select(Video).where(Video.job_id == job_id))
        if video_result.scalar_one_or_none() is None:
            db.add(Video(
                job_id=job_id,
                filename=job.filename or "",
                output_path=job.output_path,
                status="done",
                progress=100,
                message="Analyse abgeschlossen!",
            ))
            await db.flush()
        frame_row = Frame(video_id=job_id, frame_nr=frame_nr)
        db.add(frame_row)
        await db.flush()

    # Bestehende Annotation für diesen Frame überschreiben (upsert via delete+insert)
    existing = await db.execute(
        select(Annotation).where(Annotation.frame_id == frame_row.id)
    )
    for ann in existing.scalars().all():
        await db.delete(ann)

    kp_data = [kp.model_dump() for kp in body.keypoints]
    annotation = Annotation(
        frame_id=frame_row.id,
        keypoints=kp_data,
        quality_flag=1,
        annotator="user",
    )
    db.add(annotation)
    await db.commit()

    return {"saved": frame_nr}


@app.delete("/api/admin/reset", response_model=dict)
async def admin_reset_all(db: AsyncSession = Depends(get_db)) -> dict:
    """Löscht ALLE Videos, Frames, Keypoints, Annotationen und Output-Dateien."""
    result = await db.execute(delete(Video))
    await db.commit()

    with _lock:
        jobs.clear()

    deleted_files = 0
    for p in OUTPUTS_DIR.glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)
            deleted_files += 1
    for p in UPLOADS_DIR.glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)

    logger.warning("Admin-Reset: %d Videos und %d Dateien gelöscht", result.rowcount, deleted_files)
    return {"deleted_videos": result.rowcount, "deleted_files": deleted_files}


def _video_to_dict(v: "Video") -> dict:
    return {
        "job_id": v.job_id,
        "filename": v.filename,
        "horse_name": v.horse_name,
        "gait_label": v.gait_label,
        "gait_detected": v.gait_detected,
        "status": v.status,
        "training_consent": v.training_consent,
        "is_training_contribution": v.is_training_contribution,
        "output_path": v.output_path,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@app.get("/api/admin/backup/full")
async def admin_backup_full(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """ZIP: alle analysierten Videos + vollständiger DB-Export."""
    import tempfile

    v_result = await db.execute(select(Video))
    videos_json = json.dumps(
        [_video_to_dict(v) for v in v_result.scalars().all()],
        ensure_ascii=False, indent=2, default=str,
    )

    def build() -> str:
        tmp = tempfile.mktemp(suffix=".zip")
        with zipfile.ZipFile(tmp, "w") as zf:
            zf.writestr("db/videos.json", videos_json, compress_type=zipfile.ZIP_DEFLATED)
            for mp4 in OUTPUTS_DIR.glob("*.mp4"):
                zf.write(str(mp4), f"videos/{mp4.name}", compress_type=zipfile.ZIP_STORED)
        return tmp

    zip_path = await asyncio.get_running_loop().run_in_executor(None, build)
    background_tasks.add_task(lambda: Path(zip_path).unlink(missing_ok=True))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"toeltonaut_backup_full_{ts}.zip",
    )


@app.get("/api/admin/backup/learned")
async def admin_backup_learned(db: AsyncSession = Depends(get_db)) -> Response:
    """ZIP: Keypoints + Annotationen aller freigegebenen Videos (kein Videomaterial)."""
    v_result = await db.execute(
        select(Video).where(Video.training_consent == True)  # noqa: E712
    )
    videos = v_result.scalars().all()
    if not videos:
        raise HTTPException(404, "Keine freigegebenen Videos vorhanden.")

    video_ids = [v.job_id for v in videos]

    f_result = await db.execute(
        select(Frame)
        .where(Frame.video_id.in_(video_ids))
        .order_by(Frame.video_id, Frame.frame_nr)
    )
    frames = f_result.scalars().all()
    frame_ids = [f.id for f in frames]

    kp_result = await db.execute(select(Keypoint).where(Keypoint.frame_id.in_(frame_ids)))
    kp_by_frame: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        if isinstance(kp.data, list):
            kp_by_frame.setdefault(kp.frame_id, []).extend(kp.data)

    ann_result = await db.execute(select(Annotation).where(Annotation.frame_id.in_(frame_ids)))
    ann_by_frame: dict[int, list] = {
        ann.frame_id: (ann.keypoints if isinstance(ann.keypoints, list) else [])
        for ann in ann_result.scalars().all()
    }

    frames_by_video: dict[str, list] = {}
    for f in frames:
        frames_by_video.setdefault(f.video_id, []).append({
            "frame_nr": f.frame_nr,
            "timestamp_ms": f.timestamp_ms,
            "gait": f.gait,
            "is_side_view": f.is_side_view,
            "keypoints": kp_by_frame.get(f.id, []),
            "annotation": ann_by_frame.get(f.id),
        })

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "metadata.json",
            json.dumps([_video_to_dict(v) for v in videos], ensure_ascii=False, indent=2, default=str),
        )
        for vid_id, vid_frames in frames_by_video.items():
            zf.writestr(
                f"keypoints/{vid_id}.json",
                json.dumps(vid_frames, ensure_ascii=False, default=str),
            )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="toeltonaut_backup_learned_{ts}.zip"'},
    )


def _build_bulk_coco_zip(jobs_data: list[dict]) -> bytes:
    """CPU-bound: builds in-memory COCO ZIP merging all training-consented videos.

    jobs_data: list of {
        "job_id": str,
        "output_path": str,
        "frames": list[{"frame_nr": int, "timestamp_ms": float|None}],
        "ann_by_frame": {frame_nr: list_of_kp_dicts},
        "kp_by_frame": {frame_nr: list_of_kp_dicts},
    }
    Image filenames use {job_id[:8]}/frame_{frame_nr:06d}.jpg to avoid collisions.
    """
    import cv2  # type: ignore
    import numpy  # type: ignore

    coco_images = []
    coco_annotations = []
    image_jpegs: dict[str, bytes] = {}
    global_img_id = 1
    global_ann_id = 1

    for job_entry in jobs_data:
        job_id = job_entry["job_id"]
        output_path = job_entry["output_path"]
        frames = job_entry["frames"]
        ann_by_frame: dict = job_entry["ann_by_frame"]
        kp_by_frame: dict = job_entry["kp_by_frame"]
        prefix = job_id[:8]

        cap = cv2.VideoCapture(output_path)
        vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        fps_cap = cap.get(cv2.CAP_PROP_FPS) or 25.0

        for f in frames:
            frame_nr = f["frame_nr"]
            ts_ms = f["timestamp_ms"]

            # annotations take priority over keypoints (same logic as _build_coco_zip)
            kp_list = ann_by_frame.get(frame_nr) or kp_by_frame.get(frame_nr, [])
            if not kp_list:
                continue

            img_filename = f"images/{prefix}/frame_{frame_nr:06d}.jpg"

            seek_ms = ts_ms if ts_ms is not None else frame_nr * 1000.0 / fps_cap
            cap.set(cv2.CAP_PROP_POS_MSEC, seek_ms)
            ret, frame_img = cap.read()
            if ret and frame_img is not None:
                ok, buf = cv2.imencode(".jpg", frame_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if ok:
                    image_jpegs[img_filename] = buf.tobytes()
            else:
                blank = numpy.zeros((vid_h, vid_w, 3), dtype=numpy.uint8)
                _, buf = cv2.imencode(".jpg", blank, [cv2.IMWRITE_JPEG_QUALITY, 90])
                image_jpegs[img_filename] = buf.tobytes()

            kp_name_map = {e["name"]: e for e in kp_list if "name" in e}
            flat_kps: list[float] = []
            num_kps = 0

            for kp_name in _COCO_KEYPOINT_NAMES:
                e = kp_name_map.get(kp_name)
                if e and float(e.get("confidence", 0)) > 0:
                    px = float(e["x"]) * vid_w
                    py = float(e["y"]) * vid_h
                    flat_kps.extend([px, py, 2])
                    num_kps += 1
                else:
                    flat_kps.extend([0.0, 0.0, 0])

            if num_kps == 0:
                continue

            xs = [flat_kps[i * 3] for i in range(len(_COCO_KEYPOINT_NAMES)) if flat_kps[i * 3 + 2] == 2]
            ys = [flat_kps[i * 3 + 1] for i in range(len(_COCO_KEYPOINT_NAMES)) if flat_kps[i * 3 + 2] == 2]
            pad = 20.0
            bx = max(0.0, min(xs) - pad)
            by = max(0.0, min(ys) - pad)
            bw = min(float(vid_w) - bx, max(xs) - min(xs) + 2 * pad)
            bh = min(float(vid_h) - by, max(ys) - min(ys) + 2 * pad)

            coco_images.append({
                "id": global_img_id,
                "file_name": img_filename,
                "width": vid_w,
                "height": vid_h,
            })
            coco_annotations.append({
                "id": global_ann_id,
                "image_id": global_img_id,
                "category_id": 1,
                "keypoints": flat_kps,
                "num_keypoints": num_kps,
                "bbox": [bx, by, bw, bh],
                "area": bw * bh,
                "iscrowd": 0,
            })
            global_img_id += 1
            global_ann_id += 1

        cap.release()

    from datetime import datetime, timezone as _tz
    coco_doc = {
        "info": {
            "version": "1.0",
            "description": "Töltonaut Bulk Training Export",
            "date_created": datetime.now(_tz.utc).isoformat(),
        },
        "licenses": [],
        "categories": [{
            "id": 1,
            "name": "horse",
            "supercategory": "animal",
            "keypoints": _COCO_KEYPOINT_NAMES,
            "skeleton": _HORSE10_SKELETON,
        }],
        "images": coco_images,
        "annotations": coco_annotations,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("annotations/coco.json", json.dumps(coco_doc, ensure_ascii=False, indent=2))
        for img_path, img_bytes in image_jpegs.items():
            zf.writestr(img_path, img_bytes)
    return buf.getvalue()


@app.get("/api/training/export-bulk")
async def export_bulk_coco(
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Bulk COCO ZIP export: alle Videos mit training_consent=True und status='done'
    werden zu einem einzigen COCO-Datensatz zusammengeführt."""
    v_result = await db.execute(
        select(Video)
        .where(Video.training_consent == True)  # noqa: E712
        .where(Video.status == "done")
    )
    videos = v_result.scalars().all()
    if not videos:
        raise HTTPException(404, "Keine Trainingsvideos mit Freigabe vorhanden.")

    # Only include videos whose output file actually exists
    valid_videos = [v for v in videos if v.output_path and Path(v.output_path).exists()]
    if not valid_videos:
        raise HTTPException(404, "Keine Trainingsvideos mit Freigabe vorhanden.")

    video_ids = [v.job_id for v in valid_videos]

    f_result = await db.execute(
        select(Frame)
        .where(Frame.video_id.in_(video_ids))
        .order_by(Frame.video_id, Frame.frame_nr)
    )
    frames_orm = f_result.scalars().all()
    frame_ids = [f.id for f in frames_orm]

    ann_result = await db.execute(select(Annotation).where(Annotation.frame_id.in_(frame_ids)))
    ann_by_frame_id: dict[int, list] = {
        ann.frame_id: (ann.keypoints if isinstance(ann.keypoints, list) else [])
        for ann in ann_result.scalars().all()
    }

    kp_result = await db.execute(select(Keypoint).where(Keypoint.frame_id.in_(frame_ids)))
    kp_by_frame_id: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame_id.setdefault(kp.frame_id, [])
        if isinstance(kp.data, list):
            kp_by_frame_id[kp.frame_id].extend(kp.data)

    # Group frames by video_id; convert frame_id-keyed dicts to frame_nr-keyed
    frames_by_video: dict[str, list[dict]] = {}
    ann_by_frame_nr: dict[str, dict[int, list]] = {}
    kp_by_frame_nr: dict[str, dict[int, list]] = {}

    for f in frames_orm:
        frames_by_video.setdefault(f.video_id, []).append({
            "frame_nr": f.frame_nr,
            "timestamp_ms": f.timestamp_ms,
        })
        if f.id in ann_by_frame_id:
            ann_by_frame_nr.setdefault(f.video_id, {})[f.frame_nr] = ann_by_frame_id[f.id]
        if f.id in kp_by_frame_id:
            kp_by_frame_nr.setdefault(f.video_id, {})[f.frame_nr] = kp_by_frame_id[f.id]

    jobs_data = [
        {
            "job_id": v.job_id,
            "output_path": v.output_path,
            "frames": frames_by_video.get(v.job_id, []),
            "ann_by_frame": ann_by_frame_nr.get(v.job_id, {}),
            "kp_by_frame": kp_by_frame_nr.get(v.job_id, {}),
        }
        for v in valid_videos
    ]

    loop = asyncio.get_running_loop()
    zip_bytes = await loop.run_in_executor(None, _build_bulk_coco_zip, jobs_data)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="toeltonaut_training_bulk.zip"'},
    )


@app.post("/api/training/start", response_model=TrainingJobItem, status_code=202)
async def start_training(
    db: AsyncSession = Depends(get_db),
) -> TrainingJobItem:
    """Startet Fine-tuning in einem Hintergrundthread.
    Exportiert zunächst das Bulk-COCO-ZIP aus der DB, legt einen TrainingJob-Eintrag an
    und übergibt alles an start_training_thread()."""
    from .trainer import start_training_thread as _train_thread, _states, _lock as _t_lock, TrainingState

    # Prüfen ob bereits ein Training läuft
    with _t_lock:
        running = [s for s in _states.values() if s.status in ("queued", "running")]
    if running:
        raise HTTPException(409, "Ein Training läuft bereits. Bitte warten bis es abgeschlossen ist.")

    # COCO-Daten aus DB lesen (analog zu export_bulk_coco)
    v_result = await db.execute(
        select(Video).where(Video.training_consent == True).where(Video.status == "done")  # noqa: E712
    )
    valid_videos = [v for v in v_result.scalars().all() if v.output_path and Path(v.output_path).exists()]
    if not valid_videos:
        raise HTTPException(404, "Keine Trainingsvideos mit Freigabe vorhanden.")

    video_ids = [v.job_id for v in valid_videos]
    f_result = await db.execute(
        select(Frame).where(Frame.video_id.in_(video_ids)).order_by(Frame.video_id, Frame.frame_nr)
    )
    frames_orm = f_result.scalars().all()
    frame_ids = [f.id for f in frames_orm]

    ann_result = await db.execute(select(Annotation).where(Annotation.frame_id.in_(frame_ids)))
    ann_by_frame_id: dict[int, list] = {
        a.frame_id: (a.keypoints if isinstance(a.keypoints, list) else [])
        for a in ann_result.scalars().all()
    }
    kp_result = await db.execute(select(Keypoint).where(Keypoint.frame_id.in_(frame_ids)))
    kp_by_frame_id: dict[int, list] = {}
    for kp in kp_result.scalars().all():
        kp_by_frame_id.setdefault(kp.frame_id, [])
        if isinstance(kp.data, list):
            kp_by_frame_id[kp.frame_id].extend(kp.data)

    frames_by_video: dict[str, list[dict]] = {}
    ann_by_frame_nr: dict[str, dict[int, list]] = {}
    kp_by_frame_nr:  dict[str, dict[int, list]] = {}
    for f in frames_orm:
        frames_by_video.setdefault(f.video_id, []).append(
            {"frame_nr": f.frame_nr, "timestamp_ms": f.timestamp_ms}
        )
        if f.id in ann_by_frame_id:
            ann_by_frame_nr.setdefault(f.video_id, {})[f.frame_nr] = ann_by_frame_id[f.id]
        if f.id in kp_by_frame_id:
            kp_by_frame_nr.setdefault(f.video_id, {})[f.frame_nr] = kp_by_frame_id[f.id]

    jobs_data = [
        {
            "job_id":       v.job_id,
            "output_path":  v.output_path,
            "frames":       frames_by_video.get(v.job_id, []),
            "ann_by_frame": ann_by_frame_nr.get(v.job_id, {}),
            "kp_by_frame":  kp_by_frame_nr.get(v.job_id, {}),
        }
        for v in valid_videos
    ]

    # ZIP synchron im Thread-Pool generieren
    loop = asyncio.get_running_loop()
    zip_bytes: bytes = await loop.run_in_executor(None, _build_bulk_coco_zip, jobs_data)

    # ZIP in Tempfile schreiben (wird vom Training-Thread gelöscht)
    import tempfile as _tmp
    with _tmp.NamedTemporaryFile(delete=False, suffix=".zip", prefix="tlt_train_") as tf:
        tf.write(zip_bytes)
        zip_path = tf.name

    # AI-Config für Modellpfade
    from .ai_config import get_ai_config
    cfg = get_ai_config()
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    new_version = f"v0.3-finetune-{ts_tag}"
    output_model = str(MODELS_DIR / f"hrnet_w32_finetuned_{ts_tag}.pth")

    # TrainingJob in DB anlegen (output_model_path für Rollback nach Neustart)
    tj = TrainingJob(
        model_version=new_version,
        dataset_snapshot={
            "source": "bulk_export",
            "num_videos": len(valid_videos),
            "output_model_path": output_model,
        },
    )
    db.add(tj)
    await db.commit()
    await db.refresh(tj)

    # In-Memory State initialisieren
    with _t_lock:
        _states[tj.id] = TrainingState(
            job_id=tj.id,
            status="queued",
            total_epochs=50,
            output_model_path=output_model,
        )

    # Hintergrundthread starten
    threading.Thread(
        target=_train_thread,
        args=(tj.id, zip_path, cfg.pose_model or "", cfg.pose_config or "", output_model, _DB_URL_SYNC),
        daemon=True,
        name=f"training-{tj.id}",
    ).start()

    return TrainingJobItem(
        id=tj.id,
        model_version=new_version,
        mlflow_run_id=None,
        metrics=None,
        created_at=tj.created_at.isoformat(),
        status="queued",
        epoch=0,
        total_epochs=50,
    )


@app.get("/api/training/status/{job_id}", response_model=TrainingStatusResponse)
async def get_training_status(job_id: int, db: AsyncSession = Depends(get_db)) -> TrainingStatusResponse:
    """Gibt Echtzeit-Fortschritt eines laufenden oder abgeschlossenen Fine-tuning-Jobs zurück.
    Fällt auf DB zurück, wenn der In-Memory State (z.B. nach Neustart) nicht verfügbar ist."""
    from .trainer import _states, _lock as _t_lock
    with _t_lock:
        state = _states.get(job_id)
    if state:
        return TrainingStatusResponse(
            job_id=state.job_id,
            status=state.status,
            epoch=state.epoch,
            total_epochs=state.total_epochs,
            loss=state.loss,
            message=state.message,
        )
    # DB-Fallback: Status aus gespeicherten Metriken ableiten
    tj_result = await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
    tj = tj_result.scalar_one_or_none()
    if not tj:
        raise HTTPException(404, "Training-Job nicht gefunden.")
    if tj.metrics and isinstance(tj.metrics, dict):
        epochs_run = int(tj.metrics.get("epochs_run", 0))
        loss = float(tj.metrics.get("train_loss", 0.0))
        db_status = "done"
    else:
        epochs_run, loss, db_status = 0, 0.0, "queued"
    return TrainingStatusResponse(
        job_id=job_id,
        status=db_status,
        epoch=epochs_run,
        total_epochs=50,
        loss=loss,
        message="Aus Datenbank wiederhergestellt." if tj.metrics else "Kein Status verfügbar.",
    )


@app.post("/api/training/activate/{job_id}")
async def activate_model(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aktiviert ein fertig trainiertes Modell: aktualisiert config.yaml und
    invalidiert die AIConfig- und PoseEstimator-Singletons (wirkt beim nächsten Video)."""
    from .trainer import _states, _lock as _t_lock
    import yaml

    with _t_lock:
        state = _states.get(job_id)

    # TrainingJob aus DB laden
    tj_result = await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
    tj = tj_result.scalar_one_or_none()
    if not tj:
        raise HTTPException(404, "Training-Job nicht gefunden.")

    # Modellpfad: erst aus In-Memory State, dann aus DB (dataset_snapshot) – robust nach Neustart
    output_model: str | None = None
    if state and state.status == "done" and state.output_model_path:
        output_model = state.output_model_path
    elif tj.dataset_snapshot and isinstance(tj.dataset_snapshot, dict):
        output_model = tj.dataset_snapshot.get("output_model_path")

    if not output_model:
        raise HTTPException(409, "Training nicht abgeschlossen oder Modellpfad unbekannt.")
    if not Path(output_model).exists():
        raise HTTPException(404, f"Modell-Datei nicht gefunden: {output_model}")

    new_version = tj.model_version or "v0.3-finetune"

    # config.yaml aktualisieren
    config_path = Path(__file__).parent.parent / "config.yaml"
    try:
        with open(config_path) as f:
            cfg_dict = yaml.safe_load(f) or {}
        cfg_dict.setdefault("ai", {})
        cfg_dict["ai"]["pose_model"]     = output_model
        cfg_dict["ai"]["model_version"]  = new_version
        with open(config_path, "w") as f:
            yaml.dump(cfg_dict, f, allow_unicode=True, default_flow_style=False)
    except OSError as exc:
        logger.warning("config.yaml konnte nicht geschrieben werden: %s", exc)

    # Singletons invalidieren → nächster Video-Job lädt neues Modell
    import backend.app.ai_config  as _ai_mod
    import backend.app.pose_factory as _pf_mod
    _ai_mod._ai_config = None
    _pf_mod._estimator = None

    return {
        "activated":    output_model,
        "model_version": new_version,
        "job_id":       job_id,
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
