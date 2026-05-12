# Töltonaut – Projektinstruktionen für Claude Code

## Autonomer Betrieb
- Immer im Automodus arbeiten: keine Rückfragen bei Standard-Datei-, Bash- oder Leseoperationen.
- Eigenständig implementieren. Nur bei wirklich destruktiven oder nicht umkehrbaren Aktionen pausieren (Force-Push auf main, Datenbank löschen, Nutzerdaten entfernen).
- Nach jeder abgeschlossenen Arbeitseinheit einen Commit ins lokale Git-Repo erstellen.

## Virtuelles Team – immer einsetzen
Komplexe Aufgaben immer mit spezialisierten Subagenten (Agent-Tool) aufteilen:

| Rolle | Wann spawnen |
|---|---|
| **Plan**-Agent | Architekturentscheidungen, Multi-File-Refactoring, neue Features planen |
| **Explore**-Agent | Codebase-Übersichten, Muster über viele Dateien suchen |
| **general-purpose**-Agent | Recherche, Web-Suchen, mehrstufige Analysen |
| **claude-code-guide**-Agent | Fragen zu Claude API / SDK / Tooling |

- Parallele Agenten spawnen, wenn Aufgaben voneinander unabhängig sind.
- Nie im Hauptthread machen, was ein Agent schneller parallel erledigen kann.
- Ergebnisse der Agenten selbst synthetisieren – die finale Entscheidung nie delegieren.

## Git-Konventionen
- Branch: `main`
- Commit nach jeder abgeschlossenen Arbeitseinheit
- Format: `<typ>: <was geändert>` (feat, fix, docs, refactor, chore)
- Sprache: Deutsch bevorzugt

## Dokumentation aktuell halten
Die Dokumentation liegt in `docs/` als HTML-Dateien mit gemeinsamem `docs/style.css`.

**Pflicht bei Code-Änderungen:**
- Neue API-Endpunkte → `docs/developer.html` (API-Referenz-Tabellen)
- Neue Features / User Stories → `docs/product.html` (Feature-Status, Epics)
- Architektur-Änderungen → `docs/architecture.html`
- Jeder Release → `docs/changelog.html` neuer Abschnitt + `[Unveröffentlicht]` aktualisieren
- Breaking Changes → `README.md` Schnellstart/Stack-Tabelle prüfen
- Neue Umgebungsvariablen oder Config-Felder → `README.md` Konfigurations-Tabelle + `docs/developer.html`

Faustregel: Wenn sich das Verhalten der App für Nutzer oder Entwickler ändert, muss mindestens eine Docs-Datei mitgepflegt werden.

---

## Projekt: Töltonaut

**Typ:** Hobby-Projekt – kein kommerzieller Betrieb  
**Lizenzentscheidungen** gelten für nicht-kommerzielle Nutzung

KI-gestützte Bewegungsanalyse-Plattform für den **professionellen Islandpferdesport**. Kernfokus: **Tölt-Analyse**. Benutzer laden Videos hoch; die KI erkennt Skelett, Gelenke und die aktuelle Gangart und visualisiert die Bewegungsmuster im Video.

**Primärziel:** Tölt-Qualität objektiv messbar machen – Takt, Fußungssequenz, Fehlertypen.  
**In Scope:** Islandpferde, alle 5 Gangarten (Tölt priorisiert), Einzel-Pferd-Analyse, Videoanalyse  
**Out of Scope v1:** Reiter-Analyse, Multi-Pferd, Live-Turnier-Scoring, Mobile App, PDF-Report

### User Personas

**„Sigríður"** – Professionelle Reiterin, Fünfgang F1, möchte Gangfehler im Tölt objektiv sehen  
**„Jón"** – Trainer für 15 Pferde, braucht reproduzierbare Auswertungen und Exportfunktion  
**„Thomas"** – FEIF-lizenzierter Richter, nutzt App zur Nachbereitung und Ausbildung

---

## CI / Design

Dark Mode als Standard. Farbpalette mit Referenz auf die isländische Nationalflagge (Blau, Weiß, Rot) – subtil eingewoben, nicht als Flagge:

| Rolle | Name | Hex |
|---|---|---|
| Hintergrund | Vulkanschwarz | `#1A1A2E` |
| Fläche | Lavagestein | `#2D2D3A` |
| Primär hell | Gletscherblau | `#A8D8EA` |
| Primär satt | Islandflaggen-Blau | `#003F87` |
| Akzent positiv | Nordlicht-Grün | `#00C896` |
| Akzent neutral | Geysir-Weiß | `#F0F4F8` |
| Akzent Fehler/Warnung | Flaggenrot | `#C8102E` |

- **Typografie:** Inter oder Geist – professionell, nicht verspielt
- **Bildsprache:** Isländische Landschaft, Basalt, Wasser – keine Jagdmotive
- **Semantik:** Nordlicht-Grün = korrekt/positiv, Flaggenrot = Fehler/Takt-Abweichung
- **Markenzeichen:** Das frei verfügbare Wikipedia-SVG eines töltenden Islandpferds (`commons.wikimedia.org` → „Icelandic horse tölting") als zentrales UI-Element / Logo-Basis (SVG-Lizenz prüfen: meist CC BY-SA)

---

## Fachdomäne: Islandpferdesport

*Quellen: FEIF Sport Regulations 2023/2024, Islandpferd-Biomechanik-Literatur*

### Die 5 Gangarten

1. **Schritt** – 4-takt lateral
2. **Trab** – 2-takt diagonal
3. **Tölt** – 4-takt lateral, Hauptgangart, **keine Schwebephase**
4. **Galopp** – 3-takt
5. **Rennpass** – 2-takt lateral, bis 58 km/h, hat Schwebephase

Viergänger: Schritt/Trab/Tölt/Galopp | Fünfgänger: zusätzlich Rennpass

### FEIF-Bewertungssystem

Notenskala 0,0–10,0 in 0,5-Schritten. WM: 5 Richter, FEIF-lizenziert Level 1–3.  
**Disziplinen:** Tölt T1–T5, Fünfgang F1–F3, Track-Rennen V1/V2/P1/P2

**Tölt-Bewertungskriterien:** Takt → Tempo-Breite → Schwung → Hals/Kopfhaltung → Losgelassenheit → Tritt → Raumgriff → Gesamteindruck

### Kritische Bewegungsmomente

**Tölt-Fußungssequenz:** Korrekt: **HL → VL → HR → VR → HL → ...**
- Trabeinlage = VL+HR oder VR+HL simultan → Fehler/Disqualifikation
- Pass-Einlage = VL+HL oder VR+HR simultan → Fehler
- Keine Schwebephase beim Tölt

**Rennpass:** Lateral-Synchronizität VL+HL / VR+HR simultan; Versatz >15–20ms = sichtbarer Fehler; Schwebephase vorhanden = Qualitätsmerkmal

### Keypoint-Prioritäten

**Priorität 1 – Takt:** Fesselgelenk ×4 (VL/VR/HL/HR) + optional Kronrand ×4  
**Priorität 2 – Schub:** Hüftgelenk ×2, Sprunggelenk ×2, Kniegelenk Hinterbein ×2  
**Priorität 3 – Tritt:** Karpalgelenk ×2, Ellbogen ×2, Schulter ×2  
**Priorität 4 – Losgelassenheit:** Widerrist, Genick/Poll, Nasenbein  
**Rumpf-Mittellinie:** Kruppe, Lende, Rückenmitte, Widerrist, Halsansatz  
**MVP-Minimal-Set:** 4× Fesselgelenk + 2× Sprunggelenk + 2× Karpus

### Video-Aufnahme-Challenges

| Challenge | Lösung |
|---|---|
| Okklusion (innere Beine) | Symmetrie-Modell + kinematischer Prior |
| Perspektivverzerrung | Winkel statt Distanzen messen |
| Motion Blur (Rennpass) | Min. 60fps |
| Reiter als Okklusor | Separates Segmentierungs-Modell |

**Empfohlene Kamera:** Seitenansicht 90°, 10–25m, 0,8–1,5m Höhe, 60fps (Rennpass) / 30fps (Tölt)

---

## Technologie-Stack (Python)

**Backend:** FastAPI + Uvicorn  
**ML-Inferenz:** PyTorch CPU-only (GTX 1070 sm_61 inkompatibel mit PyTorch 2.1+) + Ultralytics YOLOv8 (AGPL-3.0)  
**Pose-Estimation:** MMPose (Apache 2.0) ab v0.2 – Modell `hrnet_w32_horse10` (22 KP)  
**Frontend:** React 18 + TypeScript + Vite + Tailwind CSS (Island-CI)  
**Datenbank:** PostgreSQL + SQLAlchemy async + psycopg3; psycopg3 COPY für Bulk-Writes  
**Videoverarbeitung:** OpenCV (`opencv-python-headless`) + imageio-ffmpeg  
**Job-Queue MVP:** `threading.Thread` + `queue.Queue` | **Prod:** Celery + Redis  
**ML-Training:** Python + MLflow → Modell per `config.yaml` ladbar  
**Keypoints in DB:** PostgreSQL JSONB – `[{name, x, y, confidence}]`  
**Deployment:** Docker + docker-compose

### ML-Training-Workflow

```
Horse-10 + AP-10K + eigene Videos → CVAT Annotation (COCO JSON)
  → MMPose / YOLOv8 Training → MLflow Registry
  → config.yaml: ai.model_path / ai.model_version
  → FastAPI lädt Modell beim Start
```

---

## KI-Modell & Trainingsdaten

### Modell-Strategie

```
v0.1  YOLOv8n BBox + proportionale Keypoints + regelbasierte Gangart-Erkennung
v0.2  MMPose hrnet_w32_horse10 – 22 KP, mAP ~88, kein eigenes Training nötig
      + datengestützte Gangart-Klassifikation aus Keypoint-Zeitreihen
v0.3  Fine-tuning auf nutzereigenen Islandpferd-Videos (+Sprunggelenk, +Kniegelenk HB)
```

### Gangart-Erkennung – Biomechanische Grundlagen (algo.odt)

**Kernmetriken** (aus wissenschaftlicher Literatur, AJVR 2006 / JEB):

| Gangart  | LAP        | Duty Factor | Schwebephase | Stützphasen          |
|----------|-----------|-------------|--------------|----------------------|
| Schritt  | ~25%       | 60–70%      | Nein         | 2-Bein, 3-Bein       |
| Trab     | ~50%       | 30–55%      | Ja           | 0-Bein, 2-Bein diag. |
| Galopp   | N/A        | 20–30%      | Ja           | 0-Bein, 1-Bein       |
| Tölt     | ~25%       | 30–55%      | Nein (min.)  | 1-Bein, 2-Bein       |
| Rennpass | ~0%        | <30%        | Ja           | 0-Bein, 2-Bein lat.  |

**LAP = Lateral Advanced Placement**: Zeitlicher Versatz LH→LF / T_stride (%)
- LAP wird aus Foot-On-Events berechnet: FO = lokales Y-Maximum der Fesselgelenk-Trajektorie
- T_stride = Zeitdifferenz zwischen zwei aufeinanderfolgenden LH-Foot-On-Events

**DF = Duty Factor**: Standphasenanteil pro Schrittzyklus
- Schwebephase = alle 4 DF < 50% gleichzeitig
- Tölt OHNE Schwebephase, Pass MIT Schwebephase (trotz ähnlichem LAP!)

**Tölt-Subklassifikation (FEIF):**
- LAP < 22% → Passiger Tölt ("Piggy-pace") – Rollbewegung im Sattel
- LAP 22–28% → Korrekter Tölt
- LAP > 28% → Trabiger Tölt ("Trotty Tölt") – schwer visuell zu erkennen

**Entscheidungsbaum (deterministisch, Heuristik)**:
1. LAP ≈ 50% UND DF < 50% → Trab
2. LAP ≈ 0% UND DF < 30% → Rennpass (Schwebephase)
3. LAP 15–35% UND DF ≥ 60% → Schritt (viele Stützphasen)
4. LAP 15–35% UND DF < 55% → Tölt (uni-/biped, keine Schwebephase)
5. DF < 30% (asymmetrisch) → Galopp

**Implementierung v0.1**: Proportionale KP liefern konstante Y-Werte → LAP nicht berechenbar.
Bbox-Bewegungs-Heuristik (bbox_speed, bbox_bounce) als Fallback.

**Implementierung v0.2+**: Echte ML-KP variieren → LAP + DF berechenbar.
Foot-On via lokale Maxima in geglätteter Fesselgelenk-Trajektorie.
Korrelations-Features als Backup falls Peak-Detektion scheitert.

**Open-Source-Bausteine (recherchiert)**:
- DeepLabCut SuperAnimal-Quadruped (39 KP, vortrainiert auf 40k+ Vierbeiner-Bilder)
- refineDLC: Rauschunterdrückung, Likelihood-Filterung, Interpolation
- AutoGaitA: Schrittzyklusnormierung, Feature-Extraktion
- PFERD-Dataset (2024): 3D-Mocap-Daten Pferde, CC BY, GitHub

### Keypoint-Abdeckung Horse-10 (22 KP)

Abgedeckt: Fesselgelenk ×4, Karpalgelenk ×2, Hüfte ×2, Schulter ×2, Ellbogen ×2, Widerrist, Kruppe, Poll  
**Fehlt (v0.3 annotieren):** Sprunggelenk ×2, Kniegelenk Hinterbein ×2

### Datasets (Lizenzen geprüft)

| Dataset | KP | Lizenz | Quelle |
|---|---|---|---|
| **Horse-10** (Oxford VGG) | 22 | CC BY 4.0 | `robots.ox.ac.uk/~vgg/data/horse10/` |
| **AP-10K** (NeurIPS 2021) | 17 | CC BY-NC 4.0 | `github.com/AlexTheBad/AP-10K` |

Ausgeschlossen: Animal Kingdom, EquineTrack, HorseID (Anfrage/Forschungslizenz nötig)

**Kritische Lücke:** Kein öffentliches Dataset enthält Tölt- oder Rennpass-Videos – muss selbst gesammelt werden. Nutzereigene Videos sind daher die wertvollste Trainingsquelle.

### Lern-Loop: Nutzereigene Videos

Benutzer stellen Videos zur Verfügung, mit denen die App schrittweise besser wird:

```
Nutzer lädt Video hoch + gibt Gangart-Label an
        ↓
Verarbeitung + Keypoint-Extraktion
        ↓
Keypoints + Metadaten in PostgreSQL gespeichert
        ↓
Optional: Nutzer bestätigt/korrigiert Keypoints im Browser
        ↓
COCO JSON Export → Training → neues Modell → config.yaml
```

**DB-Schema für Lern-Daten:**
- `videos` – Pfad, Gangart-Label, Quelle (eigenes Upload / Lern-Beitrag), Datum
- `frames` – video_id, frame_nr, timestamp
- `keypoints` – frame_id, `[{name, x, y, confidence}]` als JSONB
- `annotations` – frame_id, keypoints (manuell korrigiert), quality_flag, annotator
- `training_jobs` – Modellversion, Dataset-Snapshot, MLflow-Run-ID, Metriken

Nur Videos, für die der Nutzer explizit Lernfreigabe gegeben hat, fließen ins Training.

---

## Datei-Cleanup

Nach Videoverarbeitung **müssen** gelöscht werden:
- Original-Upload (`uploads/{job_id}.*`)
- Alle Zwischendateien (`*.tmp.*`, temporäre Frames)
- Ausgabedatei: Standard-TTL 24h, dann Auto-Delete (konfigurierbar)

---

## Epic & Release-Plan

### Release-Plan

| Release | Ziel |
|---|---|
| **v0.1 – MVP** | FastAPI + YOLOv8 BBox + regelbasierte Gangart-Erkennung + Island-CI + Cleanup |
| **v0.2 – Tölt-Analyse** | MMPose 22 KP, klassifikationsbasierte Gangart-Erkennung, Takt-Timeline, Login |
| **v0.3 – Vollanalyse** | Rennpass, Lern-Video-Upload |
| **v1.0 – Lernfähig** | Annotations-Loop, Modell-Verbesserung aus Nutzerdaten, DSGVO |

### Features & User Stories (Kurzform)

**F1 – Video-Upload & Verwaltung**
- US-1.1 Upload per Drag & Drop (MP4/MOV/AVI/MKV bis 4 GB) | SP 3
- US-1.2 Metadaten: Pferdename, Gangart, Datum, Kamerawinkel | SP 2
- US-1.3 Video-Bibliothek mit Filter/Sortierung/Paginierung | SP 5
- US-1.4 Datei-Cleanup: Upload+Temp nach Job, Output nach TTL | SP 3

**F2 – KI-Skelettanalyse & Gangart-Erkennung**
- US-2.0 Gangart-Erkennung: aktuelle Gangart wird live im Video eingeblendet (v0.1 regelbasiert, v0.2 klassifikationsbasiert) | SP 5
- US-2.1 Vollständige Skelett-Erkennung, >80% korrekt, farblich differenziert | SP 13
- US-2.2 **Tölt-Analyse (Kernfeature):** Fußungssequenz, Trabeinlagen, Takt-Score, Timeline | SP 8
- US-2.3 Rennpass-Analyse: Lateral-Sync, Pass-Score, Geschwindigkeit | SP 8

**F3 – Visualisierung**
- US-3.1 Video im Browser + Download, Frame-by-Frame-Navigation | SP 5
- US-3.2 Takt-Timeline: 4 Spuren (VL/VR/HL/HR), sync mit Video | SP 8
- ~~US-3.3 PDF-Report~~ – entfernt

**F4 – Lernfähigkeit**
- US-4.0 Lern-Video hochladen: Nutzer stellt Video mit Gangart-Label zur Verfügung, Keypoints + Metadaten in DB gespeichert | SP 3
- US-4.1 Browser-Annotationstool: Keypoints korrigieren, COCO JSON Export | SP 13
- US-4.2 Modellversionen verwalten, Rollback <5 Min. | SP 5
- US-4.3 PostgreSQL-Schema: videos / frames / keypoints / annotations / training_jobs | SP 8

**F5 – Design & CI**
- US-5.1 Island-CI vollständig, Dark Mode, Responsive | SP 8
- US-5.2 i18n Deutsch + Englisch, WCAG 2.1 AA | SP 5

**F6 – Infrastruktur (Python)**
- US-6.1 FastAPI + PostgreSQL + Docker | SP 8
- US-6.2 YOLOv8 v0.1 + MMPose v0.2, per config umschaltbar | SP 8
- US-6.3 OpenCV + imageio-ffmpeg, Zwei-Stufen-Encoding | SP 5
- US-6.4 React 18 + TypeScript + Vite + Tailwind | SP 13

**F7 – User-Management**
- US-7.1 E-Mail + Passwort, JWT, Passwort-Reset | SP 5
- US-7.2 DSGVO: Datenlöschung, kein Training ohne Zustimmung | SP 3

---

## Prototyp-Wissen (HorseVision)

Aus dem Python-Prototyp validierte Erkenntnisse – direkt übertragbar:

- `vid_stride=2` halbiert Verarbeitungszeit ohne merklichen Qualitätsverlust
- `YOLO_IMGSZ=640` ausreichend für Pferdeerkennung
- `conf=0.3` verhindert False Negatives bei schlechten Lichtverhältnissen
- Zwei-Stufen-Encoding (mp4v → H.264 via imageio-ffmpeg) für Browser-Kompatibilität zwingend
- `-movflags +faststart` für progressives Streaming
- Facing-Detection via Pixel-Varianz funktioniert bei Seitenaufnahmen
- Job-Recovery beim Start: `outputs/*.mp4` scannen → "done"-Einträge erstellen
- `BackgroundTasks` → `threading.Thread` für CPU-bound YOLO (nicht asyncio)
- CPU-only GTX 1070: ~6fps für 4K/60fps → ~6 Min. für 67s-Video (akzeptabel für Batch)

### Performance-Daten (Prototyp, CPU-only)

Input: `test.mov` – 4K/60fps/67s/426MB | Downscale: 3840→1920px | Output: ~18 MB H.264

### Behobene Bugs

| Bug | Fix |
|---|---|
| GTX 1070 CUDA-Fehler (sm_61 / PyTorch 2.1+) | `device="cpu"` in allen YOLO-Calls |
| ffmpeg nicht im PATH | `imageio-ffmpeg` – gebündeltes Binary |
| Job-State nach Neustart weg | `_recover_completed_jobs()` beim Start |
| Progress hängt bei ~45% (vid_stride=2) | `expected_frames = total_frames // VID_STRIDE` |

### Limitation des Prototyps (Töltonaut löst das)

- Nur 17 proportionale Keypoints – keine echte Pose-Estimation
- Keine individuellen Hufe trennbar für Takt-Analyse
- Kein FEIF-Scoring, kein Gelenk-Winkel

### Quellcode: `pose_estimator.py`

```python
import cv2, numpy as np

KEYPOINTS = [
    ("nose",         0.50, 0.06), ("left_eye",     0.44, 0.11),
    ("right_eye",    0.56, 0.11), ("poll",         0.50, 0.04),
    ("neck_base",    0.38, 0.28), ("withers",      0.36, 0.27),
    ("back_mid",     0.50, 0.29), ("croup",        0.66, 0.27),
    ("tail_base",    0.74, 0.33), ("l_shoulder",   0.30, 0.38),
    ("l_elbow",      0.26, 0.53), ("l_front_hoof", 0.24, 0.92),
    ("r_shoulder",   0.42, 0.40), ("r_front_hoof", 0.36, 0.94),
    ("l_hip",        0.62, 0.44), ("l_hind_hoof",  0.61, 0.94),
    ("r_hind_hoof",  0.72, 0.92),
]
SKELETON_EDGES = [
    (3,0,(220,220,255)),(0,1,(220,220,255)),(0,2,(220,220,255)),
    (3,4,(50,180,220)),(4,5,(50,180,220)),(5,6,(50,180,220)),
    (6,7,(50,180,220)),(7,8,(50,180,220)),
    (5,9,(100,220,100)),(9,10,(100,220,100)),(10,11,(100,220,100)),
    (5,12,(150,255,150)),(12,13,(150,255,150)),
    (7,14,(100,180,255)),(14,15,(100,180,255)),(7,16,(150,200,255)),
]

def estimate_keypoints(bbox, facing_left=True):
    x1, y1, x2, y2 = bbox
    w, h = x2-x1, y2-y1
    return [(int(x1+(1-xr if not facing_left else xr)*w), int(y1+yr*h))
            for _, xr, yr in KEYPOINTS]

def detect_facing(frame, x1, y1, x2, y2):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    w = x2-x1
    l = gray[y1:y2, x1:x1+w//3]
    r = gray[y1:y2, x2-w//3:x2]
    return float(np.std(l)) >= float(np.std(r)) if l.size and r.size else True

def draw_skeleton(frame, keypoints, confidence, bbox):
    overlay = frame.copy()
    x1, y1, x2, y2 = bbox
    cv2.rectangle(overlay, (x1,y1), (x2,y2), (50,180,50), 2)
    for i, j, color in SKELETON_EDGES:
        cv2.line(overlay, keypoints[i], keypoints[j], color, 3, cv2.LINE_AA)
    for px, py in keypoints:
        cv2.circle(overlay, (px,py), 5, (255,255,255), -1, cv2.LINE_AA)
        cv2.circle(overlay, (px,py), 5, (30,30,30), 1, cv2.LINE_AA)
    label = f"Pferd {confidence:.0%}"
    (tw,th),_ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(overlay, (x1,y1-th-8), (x1+tw+8,y1), (50,180,50), -1)
    cv2.putText(overlay, label, (x1+4,y1-4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.85, frame, 0.15, 0)
```

### Quellcode: `video_processor.py`

```python
import subprocess
from pathlib import Path
import cv2
from ultralytics import YOLO
from pose_estimator import detect_facing, draw_skeleton, estimate_keypoints

HORSE_CLASS_ID = 17
MAX_OUTPUT_WIDTH = 1920
YOLO_IMGSZ = 640
VID_STRIDE = 2

class VideoProcessor:
    def __init__(self, model_name="yolov8n.pt"):
        self.model = YOLO(model_name)

    def process(self, input_path, output_path, progress_callback):
        cap = cv2.VideoCapture(input_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        scale = MAX_OUTPUT_WIDTH/orig_w if orig_w > MAX_OUTPUT_WIDTH else 1.0
        out_w = MAX_OUTPUT_WIDTH if scale != 1.0 else orig_w
        out_h = (int(orig_h*scale) & ~1) if scale != 1.0 else orig_h
        tmp_path = output_path + ".tmp.mp4"
        out = cv2.VideoWriter(tmp_path, cv2.VideoWriter_fourcc(*"mp4v"),
                              fps/VID_STRIDE, (out_w, out_h))
        results = self.model.predict(source=input_path, stream=True,
            classes=[HORSE_CLASS_ID], verbose=False, conf=0.3,
            imgsz=YOLO_IMGSZ, device="cpu", vid_stride=VID_STRIDE)
        expected = max(1, total_frames // VID_STRIDE)
        for i, result in enumerate(results):
            frame = result.orig_img.copy()
            if scale != 1.0:
                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            if result.boxes is not None and len(result.boxes):
                b = result.boxes[int(result.boxes.conf.argmax())]
                x1,y1,x2,y2 = [int(v*scale) for v in b.xyxy[0].tolist()]
                conf = float(b.conf[0])
                kpts = estimate_keypoints((x1,y1,x2,y2), detect_facing(frame,x1,y1,x2,y2))
                frame = draw_skeleton(frame, kpts, conf, (x1,y1,x2,y2))
            out.write(frame)
            if i % 30 == 0:
                progress_callback(min(int(i/expected*90),90), f"Frame {i}/{expected}")
        out.release()
        progress_callback(92, "Konvertiere...")
        _transcode_h264(tmp_path, output_path)
        Path(tmp_path).unlink(missing_ok=True)
        progress_callback(100, "Fertig!")

def _transcode_h264(src, dst):
    import imageio_ffmpeg, shutil
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", src,
        "-vcodec", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart", "-an", dst], capture_output=True)
    if r.returncode != 0:
        shutil.copy2(src, dst)
```

### Quellcode: `main.py`

```python
import threading, uuid
from pathlib import Path
import aiofiles
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from models import JobState, JobStatus, UploadResponse
from video_processor import VideoProcessor

BASE_DIR = Path(__file__).parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
FRONTEND_DIR = BASE_DIR / "frontend"
for d in (UPLOADS_DIR, OUTPUTS_DIR): d.mkdir(exist_ok=True)

app = FastAPI(title="Töltonaut")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

jobs: dict[str, JobState] = {}
_lock = threading.Lock()
_processor, _processor_lock = None, threading.Lock()

def _recover_completed_jobs():
    for mp4 in OUTPUTS_DIR.glob("*.mp4"):
        if mp4.stem not in jobs:
            jobs[mp4.stem] = JobState(job_id=mp4.stem, input_path="",
                output_path=str(mp4), status="done", progress=100,
                message="Analyse abgeschlossen!")

_recover_completed_jobs()

def get_processor():
    global _processor
    with _processor_lock:
        if _processor is None:
            _processor = VideoProcessor()
    return _processor

def run_processing(job_id):
    with _lock: jobs[job_id].status = "processing"
    def cb(pct, msg):
        with _lock: jobs[job_id].progress, jobs[job_id].message = pct, msg
    try:
        get_processor().process(jobs[job_id].input_path, jobs[job_id].output_path, cb)
        with _lock: jobs[job_id].status, jobs[job_id].progress = "done", 100
    except Exception as e:
        with _lock: jobs[job_id].status, jobs[job_id].message = "error", f"Fehler: {e}"

@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mov").suffix.lower()
    if suffix not in {".mp4",".mov",".avi",".mkv",".webm"}:
        raise HTTPException(400, "Nicht unterstütztes Format.")
    job_id = str(uuid.uuid4())
    input_path = str(UPLOADS_DIR / f"{job_id}{suffix}")
    output_path = str(OUTPUTS_DIR / f"{job_id}.mp4")
    async with aiofiles.open(input_path, "wb") as f:
        while chunk := await file.read(1024*1024): await f.write(chunk)
    with _lock: jobs[job_id] = JobState(job_id=job_id, input_path=input_path, output_path=output_path)
    background_tasks.add_task(run_processing, job_id)
    return UploadResponse(job_id=job_id, filename=file.filename or "video")

@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    with _lock: job = jobs.get(job_id)
    if not job: raise HTTPException(404, "Job nicht gefunden.")
    return JobStatus(job_id=job.job_id, status=job.status, progress=job.progress, message=job.message)

@app.get("/api/download/{job_id}")
async def download_result(job_id: str):
    with _lock: job = jobs.get(job_id)
    if not job or job.status != "done": raise HTTPException(404, "Nicht verfügbar.")
    return FileResponse(job.output_path, media_type="video/mp4",
                        filename=f"toeltonaut_{job_id[:8]}.mp4")

@app.delete("/api/job/{job_id}")
async def delete_job(job_id: str):
    with _lock: job = jobs.pop(job_id, None)
    if not job: raise HTTPException(404, "Job nicht gefunden.")
    Path(job.input_path).unlink(missing_ok=True)
    Path(job.output_path).unlink(missing_ok=True)
    return {"deleted": job_id}

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
```
