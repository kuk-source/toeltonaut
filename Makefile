.PHONY: build build-deps test run logs down clean

# ── Schneller Deps-Test: nur Python-Abhängigkeiten, kein Modell-Download ──────
# Dauert ~5 Min (torch-Layer gecacht: <1 Min). Zeigt Fehler bevor der volle
# Build (inkl. 109 MB Modell-Download) gestartet wird.
build-deps:
	docker build --network=host --target deps -t toeltonaut-deps backend/

# ── Voller Produktions-Build ──────────────────────────────────────────────────
build:
	docker compose build

# ── Import-Test im deps-Image ─────────────────────────────────────────────────
test-imports: build-deps
	docker run --rm toeltonaut-deps python -c "\
import mmcv, mmengine, mmpose, cv2, torch, ultralytics; \
print('torch', torch.__version__); \
print('mmcv', mmcv.__version__); \
print('mmpose', mmpose.__version__); \
print('ALL OK'); \
"

# ── App starten ───────────────────────────────────────────────────────────────
run:
	docker compose up

# ── App neu bauen und starten ─────────────────────────────────────────────────
rebuild:
	docker compose up --build

# ── Logs folgen ───────────────────────────────────────────────────────────────
logs:
	docker compose logs -f backend

# ── Stoppen ───────────────────────────────────────────────────────────────────
down:
	docker compose down

# ── Alles aufräumen (inkl. Volumes) ──────────────────────────────────────────
clean:
	docker compose down -v
	docker rmi toeltonaut-deps 2>/dev/null || true
