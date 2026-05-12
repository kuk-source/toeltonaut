FROM python:3.12-slim AS deps

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 ffmpeg wget gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# ── PyTorch CPU-only ───────────────────────────────────────────────────────────
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# ── pycocotools + numpy ────────────────────────────────────────────────────────
RUN pip install --no-cache-dir pycocotools numpy

# ── chumpy: altes Build-System, braucht --no-build-isolation ─────────────────
RUN pip install --no-cache-dir --no-build-isolation chumpy

# ── xtcocotools-Stub als echtes Pip-Paket (tarball fehlt _mask.c) ─────────────
RUN python3 -c "\
import os; \
os.makedirs('/tmp/xt/xtcocotools', exist_ok=True); \
open('/tmp/xt/setup.py','w').write(\"from setuptools import setup,find_packages\nsetup(name='xtcocotools',version='1.14.3',packages=find_packages())\n\"); \
open('/tmp/xt/xtcocotools/__init__.py','w').write(''); \
open('/tmp/xt/xtcocotools/coco.py','w').write('from pycocotools.coco import COCO\n'); \
open('/tmp/xt/xtcocotools/cocoeval.py','w').write('from pycocotools.cocoeval import COCOeval\n'); \
open('/tmp/xt/xtcocotools/mask.py','w').write('from pycocotools import mask;from pycocotools.mask import *\n'); \
open('/tmp/xt/xtcocotools/version.py','w').write(\"__version__='1.14.3'\n\"); \
" && pip install --no-cache-dir /tmp/xt && rm -rf /tmp/xt

# ── mmcv-lite: mmcv ohne C++-Extensions (MMCV_WITH_OPS=0 benennt das Paket um)
# Für HRNet CPU-Inference nicht nötig. Spart g++ und ~10 Min Compile-Zeit.
RUN pip install --no-cache-dir --no-build-isolation "mmcv-lite>=2.0.0,<3.0.0"

# ── mmengine + mmpose ──────────────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    "mmengine>=0.6.0,<1.0.0" \
    "mmpose==1.3.2"

# ── Post-Install-Patch mmpose 1.3.2: optionale Heads deaktivieren ─────────────
# RTMOHead  → braucht mmdet | EDPoseHead → braucht mmcv._ext (nicht in mmcv-lite)
# Wir nutzen nur HRNet – RTMOHead/EDPoseHead werden nie aufgerufen.
RUN SP=/usr/local/lib/python3.12/site-packages && \
    sed -i '/from .rtmo_head import RTMOHead/d' \
        $SP/mmpose/models/heads/hybrid_heads/__init__.py && \
    sed -i \
        -e 's/from .hybrid_heads import DEKRHead, RTMOHead, VisPredictHead/from .hybrid_heads import DEKRHead, VisPredictHead/' \
        -e '/from .transformer_heads import EDPoseHead/d' \
        -e "s/'RTMOHead', \?//g; s/'RTMOHead'//g" \
        -e "s/'EDPoseHead', \?//g; s/'EDPoseHead'//g" \
        $SP/mmpose/models/heads/__init__.py && \
    echo 'mmpose heads patched OK'

# ── App-Abhängigkeiten ─────────────────────────────────────────────────────────
COPY requirements.txt .
RUN grep -v "^torch\|^torchvision\|extra-index-url\|^mmcv\|^mmpose\|^mmengine" requirements.txt \
    | pip install --no-cache-dir -r /dev/stdin

# ── Import-Smoke-Test (kein Modell nötig) ─────────────────────────────────────
RUN python -c "import mmcv, mmengine, mmpose; print('mmcv', mmcv.__version__, '/ mmpose', mmpose.__version__, '– OK')"

# ════════════════════════════════════════════════════════════════════════════════
FROM deps AS prod

# ── Modell-Verzeichnis und MMPose-Config ───────────────────────────────────────
# Modelle VOR dem App-Code kopieren: Modell-Layer werden gecacht und müssen
# bei rein-Code-Änderungen nicht neu gebaut / heruntergeladen werden.
RUN mkdir -p /app/models
COPY models/horse10_hrnet_w32_1x.py /app/models/

# ── Horse-10 Checkpoint ────────────────────────────────────────────────────────
RUN wget -q -O /app/models/hrnet_w32_horse10_256x256_split1.pth \
    "https://download.openmmlab.com/mmpose/animal/hrnet/hrnet_w32_horse10_256x256_split1-401d901a_20210405.pth"

# ── YOLO-Modelle vorladen (Detection + Segmentation) ─────────────────────────
RUN pip install --no-cache-dir "lap>=0.5.12"
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# ── Smoke-Test: MMPose + Horse-10 laden ───────────────────────────────────────
RUN python -c "\
from mmpose.apis import init_model; \
m = init_model('/app/models/horse10_hrnet_w32_1x.py', \
               '/app/models/hrnet_w32_horse10_256x256_split1.pth', device='cpu'); \
print('MMPose Horse-10 OK –', m.dataset_meta.get('num_keypoints', '?'), 'KP'); \
"

# ── App-Code (nach Modellen – so wird der Modell-Layer gecacht) ───────────────
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
