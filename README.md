# 🐴 Töltonaut

**KI-gestützte Bewegungsanalyse für den professionellen Islandpferdesport**

Töltonaut analysiert Videos von Islandpferden und macht Tölt-Qualität objektiv messbar. Die KI erkennt Skelett und Gelenke, identifiziert die aktuelle Gangart und bewertet Takt, Fußungssequenz und Fehlertypen nach FEIF-Richtlinien.

> Hobby-Projekt · Nicht-kommerziell · Python + React

---

## Features

- **Skelett-Overlay** – YOLOv8 + MMPose erkennen Pferd und zeichnen 22 Keypoints ein (Horse-10 Schema)
- **Gangart-Erkennung** – Tölt, Trab, Schritt, Galopp, Rennpass via LAP/DF-Biomechanik
- **Tölt-Scoring** – FEIF-konforme Bewertung mit Subklassifikation (passig/korrekt/trabig), LAP, Duty Factor
- **Rennpass-Scoring** – Lateral-Synchronizität, Schwebephase, Stride Count
- **Takt-Timeline** – 4-spurige Huf-Landungs-Visualisierung (VL/VR/HL/HR), sync mit Video
- **Geschwindigkeitsschätzung** – Schrittlänge × Schrittfrequenz, stockmaßnormiert
- **Keypoint-Rendering** – Lag-freie Darstellung via `requestVideoFrameCallback`
- **Annotationstool** – Keypoints manuell korrigieren mit Zoom/Pan, Undo/Redo, Tastatur-Navigation, COCO-JSON-Export
- **Lernfähig** – Nutzereigene Videos verbessern das Modell (1-Klick Fine-tuning, Rollback)
- **i18n** – Deutsch und Englisch (react-i18next)
- **Auth** – JWT-Login/Register, Account-Löschung (DSGVO)
- **Island-Design** – Dark Mode mit Isländischer Farbpalette, WCAG 2.1 AA

---

## Stack

| Schicht | Technologie |
|---|---|
| Backend | Python 3.12 · FastAPI · Uvicorn |
| ML | YOLOv8n (CPU-only) · MMPose hrnet_w32_horse10 |
| Datenbank | PostgreSQL 16 · SQLAlchemy async · psycopg3 |
| Video | OpenCV · imageio-ffmpeg · H.264 |
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS · react-i18next |
| Auth | JWT (HS256) · bcrypt |
| Infra | Docker · Docker Compose |

---

## Voraussetzungen

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2.20

---

## Schnellstart

```bash
# Repository klonen
git clone <repo-url>
cd Töltonaut

# Umgebungsvariablen einrichten (JWT-Secret und DB-Passwort)
cp .env.example .env
# .env öffnen und SECRET_KEY setzen

# Alle Services starten
docker compose up
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

Beim **ersten Start** wird das Backend-Image gebaut und npm-Pakete installiert – das dauert 3–5 Minuten.

---

## Weitere Start-Optionen

```bash
# Im Hintergrund starten
docker compose up -d

# Logs beobachten
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild erzwingen (nach Code-Änderungen am Backend)
docker compose up --build backend

# Einzelnen Service neu starten
docker compose restart backend

# Alle Services stoppen und Volumes behalten
docker compose down

# Alles inkl. Volumes löschen (Datenbank zurücksetzen)
docker compose down -v
```

---

## Konfiguration

### `backend/config.yaml`

```yaml
ai:
  model_version: "v0.1"        # v0.1 (proportional) | v0.2-mmpose (22 KP)
  model_path: "yolov8n.pt"
  device: "cpu"                # cpu | cuda | mps
  yolo_conf: 0.3
  yolo_imgsz: 640
  vid_stride: 2                # Frames überspringen (2 = halbe Verarbeitungszeit)
  max_output_width: 1920

output:
  ttl_hours: 24                # Auto-Delete verarbeiteter Videos nach N Stunden
```

### Umgebungsvariablen (.env)

Kopiere `.env.example` zu `.env` und passe die Werte an:

| Variable | Beschreibung | Docker-Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL DSN (psycopg3) | `postgresql+psycopg://toeltonaut:toeltonaut@db:5432/toeltonaut` |
| `UPLOADS_DIR` | Pfad für hochgeladene Videos | `/data/uploads` |
| `OUTPUTS_DIR` | Pfad für verarbeitete Videos | `/data/outputs` |
| `SECRET_KEY` | JWT-Signing-Key | — ⚠️ **Pflicht in Produktion** |
| `CORS_ORIGINS` | Erlaubte CORS-Origins (kommagetrennt) | `http://localhost:5173,http://localhost:3000` |
| `OUTPUT_TTL_HOURS` | Auto-Delete nach N Stunden | `24` |
| `UPLOAD_TTL_HOURS` | Upload-Datei nach Verarbeitung behalten | `0` (sofort löschen) |

> **Produktion:** `SECRET_KEY` in `.env` setzen – niemals den Default verwenden.

---

## KI-Modell wechseln (v0.1 → v0.2)

```bash
# 1. MMPose im Backend-Container installieren
docker compose exec backend pip install mmengine mmcv mmdet mmpose

# 2. Modell-Checkpoint herunterladen
docker compose exec backend mim download mmpose \
  --config td-hm_hrnet-w32_8xb64-100e_horse10-256x256 --dest .

# 3. config.yaml aktualisieren
#    model_version: "v0.2-mmpose"
#    pose_model: "hrnet_w32_horse10"

# 4. Backend neu starten
docker compose restart backend
```

---

## Lokale Entwicklung ohne Docker

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# PyTorch CPU zuerst (wichtig – verhindert CUDA-Inkompatibilität)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg://toeltonaut:toeltonaut@localhost:5432/toeltonaut"
export SECRET_KEY="dev-key"
# oder: cp .env.example .env && source .env

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # Dev-Server: http://localhost:5173
npm run build        # Produktions-Build → frontend/dist/
npm run preview      # Build lokal testen
```

---

## Projektstruktur

```
Töltonaut/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI Entry-Point
│   │   ├── video_processor.py   # ML-Pipeline
│   │   ├── gait_detector.py     # Gangart-Erkennung
│   │   ├── tolt_scorer.py       # Tölt-Scoring
│   │   ├── rennpass_scorer.py   # Rennpass-Scoring
│   │   ├── pose_factory.py      # v0.1/v0.2 Modell-Auswahl
│   │   ├── db_models.py         # SQLAlchemy ORM
│   │   └── auth.py              # JWT + bcrypt
│   ├── config.yaml              # KI-Konfiguration
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/client.ts        # Alle API-Aufrufe
│   │   ├── components/          # React-Komponenten
│   │   └── locales/             # i18n DE/EN
│   └── package.json
├── docs/                        # Dokumentation (HTML)
│   ├── index.html
│   ├── architecture.html
│   ├── developer.html
│   ├── product.html
│   ├── user-manual.html
│   └── changelog.html
├── docker-compose.yml
└── README.md
```

---

## Dokumentation

Vollständige Dokumentation im [`docs/`](docs/) Verzeichnis:

| Dokument | Inhalt |
|---|---|
| [Architektur](docs/architecture.html) | Systemübersicht, Komponenten, DB-Schema, ML-Pipeline |
| [Entwickler](docs/developer.html) | Setup, API-Referenz, Backend/Frontend-Guide |
| [Produkt](docs/product.html) | Vision, Personas, Roadmap, FEIF-Domänenwissen |
| [Benutzerhandbuch](docs/user-manual.html) | Video hochladen, Ergebnisse verstehen, FAQ |
| [Changelog](docs/changelog.html) | Versionshistorie |

---

## API-Überblick

```
POST   /api/upload                  Video hochladen, Job starten
GET    /api/status/{job_id}         Job-Status & Fortschritt
GET    /api/videos                  Video-Bibliothek
GET    /api/download/{job_id}       Verarbeitetes Video herunterladen
DELETE /api/job/{job_id}            Job und Dateien löschen

GET    /api/takt-timeline/{job_id}  Huf-Landungs-Timeline
GET    /api/toelt-score/{job_id}    Tölt-Score (0–10, FEIF)
GET    /api/rennpass-score/{job_id} Rennpass-Score

GET    /api/frame/{id}/{nr}         Frame als JPEG
GET    /api/keypoints/{id}/{nr}     Keypoints für Frame
POST   /api/annotations/{id}/{nr}   Keypoints korrigieren

POST   /api/auth/register           Registrieren
POST   /api/auth/login              Login → JWT
GET    /api/auth/me                 Aktueller User
DELETE /api/auth/account            Account löschen (DSGVO)

GET    /api/stats                   Globale Statistiken
GET    /health                      Health Check
```

Vollständige interaktive Dokumentation: `http://localhost:8000/docs`

---

## Lizenz

Dieses Projekt ist ein **nicht-kommerzielles Hobby-Projekt**.

- **YOLOv8:** AGPL-3.0 (Ultralytics)
- **Horse-10 Dataset:** CC BY 4.0
- **AP-10K Dataset:** CC BY-NC 4.0

---

## Hintergrund

Töltonaut entstand aus der Beobachtung, dass professionelle Islandpferd-Reiter keine objektiven Werkzeuge haben, um Tölt-Fehler zu analysieren. Das FEIF-Bewertungssystem ist subjektiv und von erfahrenen Richtern abhängig. Töltonaut macht Takt, Fußungssequenz und typische Fehler wie Trabeinlagen frame-genau sichtbar.

Die 5 Gangarten des Islandpferds – Schritt, Trab, **Tölt**, Galopp und Rennpass – sind einzigartig in der Pferdewelt. Der Tölt als 4-taktiger Lateralgang ohne Schwebephase ist das Herz des Islandpferdsports und der primäre Fokus dieser App.
