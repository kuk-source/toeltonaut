from pathlib import Path
import os

# ai_config darf NICHT config.py importieren (zirkuläre Importe vermeiden).
# config.py importiert ai_config – Richtung ist immer config → ai_config.
from .ai_config import get_ai_config as _get_ai_config

_ai = _get_ai_config()

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://toeltonaut:toeltonaut@localhost:5432/toeltonaut",
)

UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "/data/uploads"))
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "/data/outputs"))
# Trained/fine-tuned models landen im persistenten Volume, nicht im Image-Layer
MODELS_DIR  = Path(os.getenv("MODELS_DIR",  "/data/models"))
OUTPUT_TTL_HOURS = int(os.getenv("OUTPUT_TTL_HOURS", "24"))
UPLOAD_TTL_HOURS = int(os.getenv("UPLOAD_TTL_HOURS", str(_ai.upload_ttl_hours)))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "4096"))

# Werte aus config.yaml, überschreibbar via Umgebungsvariablen.
YOLO_MODEL = os.getenv("YOLO_MODEL", _ai.model_path)
YOLO_CONF = float(os.getenv("YOLO_CONF", str(_ai.yolo_conf)))
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", str(_ai.yolo_imgsz)))
VID_STRIDE = int(os.getenv("VID_STRIDE", str(_ai.vid_stride)))
MAX_OUTPUT_WIDTH = int(os.getenv("MAX_OUTPUT_WIDTH", str(_ai.max_output_width)))

SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
_DEFAULT_SECRET = "dev-secret-key-change-in-production"

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]

for _d in (UPLOADS_DIR, OUTPUTS_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
