"""
Proportionale Keypoints für v0.1 – Horse-10 Schema (22 KP).

Indizes sind identisch mit mmpose_estimator.py / HORSE10_KEYPOINTS, damit
gait_detector, tolt_scorer und rennpass_scorer bei beiden Estimatoren funktionieren.

Koordinaten (x_ratio, y_ratio) gelten für horse facing LEFT (Nase zeigt nach links).
Bei facing_right wird x gespiegelt: x_pixel = x1 + (1 - x_ratio) * w.
"""
import cv2
import numpy as np

# (name, x_ratio, y_ratio) – facing left, x: 0=Nase, 1=Schweif; y: 0=oben, 1=unten
KEYPOINTS: list[tuple[str, float, float]] = [
    # Kopf
    ("nose",            0.05, 0.10),   # 0
    ("left_eye",        0.09, 0.07),   # 1  (near eye, sichtbare Seite)
    ("right_eye",       0.11, 0.07),   # 2  (far eye, abgewandte Seite)
    ("left_ear",        0.08, 0.02),   # 3
    ("right_ear",       0.10, 0.02),   # 4
    ("throat",          0.15, 0.20),   # 5
    # Rückenlinie
    ("withers",         0.30, 0.22),   # 6  Widerrist – höchster Punkt
    ("tail_base",       0.88, 0.30),   # 7  Schweifansatz
    # Hufe (Bodenkontakt, Prio 1 für Takt)
    ("l_front_hoof",    0.22, 0.97),   # 8
    ("r_front_hoof",    0.27, 0.97),   # 9
    ("l_hind_hoof",     0.74, 0.97),   # 10
    ("r_hind_hoof",     0.80, 0.97),   # 11
    # Fesselgelenke – INDIZES 12–15 – Prio 1, von gait_detector verwendet
    ("l_front_fetlock", 0.22, 0.87),   # 12
    ("r_front_fetlock", 0.27, 0.87),   # 13
    ("l_hind_fetlock",  0.74, 0.87),   # 14
    ("r_hind_fetlock",  0.80, 0.87),   # 15
    # Karpalgelenke (Vorderbein) + Stifle/Kniegelenk (Hinterbein) – Prio 2
    ("l_front_knee",    0.23, 0.63),   # 16  Karpalgelenk VL
    ("r_front_knee",    0.28, 0.63),   # 17  Karpalgelenk VR
    ("l_hind_knee",     0.71, 0.58),   # 18  Kniegelenk HL (Stifle)
    ("r_hind_knee",     0.76, 0.58),   # 19  Kniegelenk HR (Stifle)
    # Hüfte – Prio 2
    ("l_hip",           0.75, 0.38),   # 20
    ("r_hip",           0.80, 0.40),   # 21
    # Schultergelenk + Ellbogengelenk – Vorderbein Prio 3
    ("l_shoulder",      0.24, 0.35),   # 22  Schultergelenk VL
    ("r_shoulder",      0.29, 0.35),   # 23  Schultergelenk VR
    ("l_elbow",         0.22, 0.50),   # 24  Ellbogengelenk VL
    ("r_elbow",         0.27, 0.50),   # 25  Ellbogengelenk VR
    # Sprunggelenk (Tarsus) – Hinterbein Prio 2
    ("l_hock",          0.73, 0.72),   # 26  Sprunggelenk HL
    ("r_hock",          0.78, 0.72),   # 27  Sprunggelenk HR
    # Topline-Punkte für Rücken-Analyse und Gangart-Klassifikation
    ("poll",            0.12, 0.05),   # 28  Genick (Hals-Kopf-Übergang) – Kopf-Hals-Winkel
    ("back_mid",        0.58, 0.26),   # 29  Rückenmitte – Topline-Oszillation
    ("croup",           0.78, 0.23),   # 30  Kruppe (Tuber sacrale) – Becken-Bewegung
]

# Fetlock-Indizes – müssen mit gait_detector.py und tolt_scorer.py übereinstimmen
FETLOCK_INDICES = {
    "l_front": 12,
    "r_front": 13,
    "l_hind":  14,
    "r_hind":  15,
}

# Island-CI Farben (BGR)
_GLETSCHERBLAU = (234, 216, 168)
_NORDLICHT     = (150, 200,   0)
_FLAGGENROT    = ( 46,  16, 200)
_ISLANDBLAU    = (135,  63,   0)
_GEYSIRWEISS   = (248, 244, 240)
_LAVAGESTEIN   = ( 58,  45,  45)
_GRUEN_FERN    = (100, 180, 100)   # Farbe für abgewandte (far) Vorderbein-Seite
_BLAU_FERN     = (200, 180, 120)   # Farbe für abgewandte (far) Hinterbein-Seite

# Skelett-Kanten: (idx_a, idx_b, bgr_farbe)
SKELETON_EDGES: list[tuple[int, int, tuple[int, int, int]]] = [
    # Kopf
    (0,  1, _GLETSCHERBLAU),   # Nase → linkes Auge
    (0,  2, _GLETSCHERBLAU),   # Nase → rechtes Auge
    (1,  3, _GLETSCHERBLAU),   # linkes Auge → linkes Ohr
    (2,  4, _GLETSCHERBLAU),   # rechtes Auge → rechtes Ohr
    (0,  5, _ISLANDBLAU),      # Nase → Kehle
    (5, 28, _ISLANDBLAU),      # Kehle → Genick (Halsunterlinie)
    (28,  6, _ISLANDBLAU),     # Genick → Widerrist (Halsoberlinie)
    # Vollständige Rückenlinie: Widerrist → Rückenmitte → Kruppe → Schweifansatz
    (6,  29, _ISLANDBLAU),     # Widerrist → Rückenmitte
    (29, 30, _ISLANDBLAU),     # Rückenmitte → Kruppe
    (30,  7, _ISLANDBLAU),     # Kruppe → Schweifansatz
    # Vorderbein nahe: Widerrist → Schulter → Ellbogen → Karpus → Fessel → Huf
    (6,  22, _NORDLICHT),      # Widerrist → Schultergelenk VL
    (22, 24, _NORDLICHT),      # Schulter → Ellbogen VL
    (24, 16, _NORDLICHT),      # Ellbogen → Karpalgelenk VL
    (16, 12, _NORDLICHT),      # Karpus → Fesselgelenk VL
    (12,  8, _NORDLICHT),      # Fessel → Huf VL
    # Vorderbein fern (r = far side)
    (6,  23, _GRUEN_FERN),
    (23, 25, _GRUEN_FERN),
    (25, 17, _GRUEN_FERN),
    (17, 13, _GRUEN_FERN),
    (13,  9, _GRUEN_FERN),
    # Hinterbein nahe: Kruppe → Hüfte → Stifle → Sprunggelenk → Fessel → Huf
    (30, 20, _ISLANDBLAU),     # Kruppe → Hüfte L
    (20, 18, _GLETSCHERBLAU),  # Hüfte → Stifle HL
    (18, 26, _GLETSCHERBLAU),  # Stifle → Sprunggelenk HL
    (26, 14, _GLETSCHERBLAU),  # Sprunggelenk → Fesselgelenk HL
    (14, 10, _GLETSCHERBLAU),  # Fessel → Huf HL
    # Hinterbein fern: Kruppe → Hüfte R → ...
    (30, 21, _ISLANDBLAU),
    (21, 19, _BLAU_FERN),
    (19, 27, _BLAU_FERN),
    (27, 15, _BLAU_FERN),
    (15, 11, _BLAU_FERN),
]


def estimate_keypoints(
    bbox: tuple[int, int, int, int],
    facing_left: bool = True,
) -> list[tuple[int, int]]:
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    pts = []
    for _, xr, yr in KEYPOINTS:
        px = x1 + int((xr if facing_left else 1.0 - xr) * w)
        py = y1 + int(yr * h)
        pts.append((px, py))
    return pts


def detect_facing(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
) -> bool:
    """True = Pferd schaut nach links."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    w = x2 - x1
    left_crop  = gray[y1:y2, x1:x1 + w // 3]
    right_crop = gray[y1:y2, x2 - w // 3:x2]
    if left_crop.size == 0 or right_crop.size == 0:
        return True
    return float(np.std(left_crop)) >= float(np.std(right_crop))


def draw_skeleton(
    frame: np.ndarray,
    keypoints: list[tuple[int, int]],
    confidence: float,
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    overlay = frame.copy()
    x1, y1, x2, y2 = bbox
    cv2.rectangle(overlay, (x1, y1), (x2, y2), _NORDLICHT, 2)

    for i, j, color in SKELETON_EDGES:
        if i < len(keypoints) and j < len(keypoints):
            cv2.line(overlay, keypoints[i], keypoints[j], color, 2, cv2.LINE_AA)

    # Größere Punkte für Fesselgelenke, Hufe (Prio 1) und Topline-Punkte
    for idx, (px, py) in enumerate(keypoints):
        radius = 6 if idx in (8, 9, 10, 11, 12, 13, 14, 15, 26, 27, 29, 30) else 4
        cv2.circle(overlay, (px, py), radius, _GEYSIRWEISS, -1, cv2.LINE_AA)
        cv2.circle(overlay, (px, py), radius, _LAVAGESTEIN,  1, cv2.LINE_AA)

    label = f"Pferd {confidence:.0%}"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(overlay, (x1, y1 - th - 8), (x1 + tw + 8, y1), _NORDLICHT, -1)
    cv2.putText(overlay, label, (x1 + 4, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, _LAVAGESTEIN, 2, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.85, frame, 0.15, 0)


def draw_keypoints_small(
    frame: np.ndarray,
    keypoints: list[tuple[int, int]],
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    overlay = frame.copy()
    for i, j, color in SKELETON_EDGES:
        if i < len(keypoints) and j < len(keypoints):
            cv2.line(overlay, keypoints[i], keypoints[j], color, 1, cv2.LINE_AA)
    for px, py in keypoints:
        cv2.circle(overlay, (px, py), 3, _GEYSIRWEISS, -1, cv2.LINE_AA)
        cv2.circle(overlay, (px, py), 3, _LAVAGESTEIN,  1, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.60, frame, 0.40, 0)


def draw_subject_outline(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """iOS-Sticker-Kontureffekt: saubere Maske → zwei Glow-Schichten + präziser Rand."""
    GLOW_BGR  = np.array([234, 216, 168], dtype=np.float32)  # Gletscherblau
    EDGE_BGR  = np.array([248, 244, 240], dtype=np.float32) * 0.75 + GLOW_BGR * 0.25  # hell-blau

    # 1. Maske bereinigen: Löcher schließen, Jaggies durch leichten Blur weichzeichnen
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)
    mask_smooth = cv2.GaussianBlur(mask_clean.astype(np.float32), (0, 0), sigmaX=1.5)
    mask_bin = (mask_smooth > 64).astype(np.uint8) * 255

    # 2. Enger Halo (~10px), mittlere Intensität
    k_near = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    near_raw = cv2.subtract(cv2.dilate(mask_bin, k_near), mask_bin)
    near_blur = cv2.GaussianBlur(near_raw.astype(np.float32), (0, 0), sigmaX=5)
    alpha_near = (near_blur / 255.0 * 0.55).clip(0.0, 1.0)

    # 3. Weiter Glow (~30px), sehr fein
    k_far = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))
    far_raw = cv2.subtract(cv2.dilate(mask_bin, k_far), mask_bin)
    far_blur = cv2.GaussianBlur(far_raw.astype(np.float32), (0, 0), sigmaX=16)
    alpha_far = (far_blur / 255.0 * 0.28).clip(0.0, 1.0)

    # 4. Präziser Rand: morphologischer Gradient (dilate − erode = gleichmäßige Linie)
    k_edge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    edge = cv2.subtract(cv2.dilate(mask_bin, k_edge), cv2.erode(mask_bin, k_edge))
    alpha_edge = (edge.astype(np.float32) / 255.0 * 0.92).clip(0.0, 1.0)

    result = frame.astype(np.float32)
    result = result * (1 - alpha_far[:, :, None])  + GLOW_BGR  * alpha_far[:, :, None]
    result = result * (1 - alpha_near[:, :, None]) + GLOW_BGR  * alpha_near[:, :, None]
    result = result * (1 - alpha_edge[:, :, None]) + EDGE_BGR  * alpha_edge[:, :, None]
    return result.clip(0, 255).astype(np.uint8)


def draw_gait_overlay(frame: np.ndarray, gait: str | None) -> np.ndarray:
    overlay = frame.copy()
    h, w = frame.shape[:2]

    gait_map = {
        "Tölt":     (_NORDLICHT,     "Tölt"),
        "Tolt":     (_NORDLICHT,     "Tölt"),
        "Trab":     (_GLETSCHERBLAU, "Trab"),
        "Schritt":  (_GLETSCHERBLAU, "Schritt"),
        "Galopp":   (_GLETSCHERBLAU, "Galopp"),
        "Rennpass": (_GLETSCHERBLAU, "Rennpass"),
        "Unbekannt":(_FLAGGENROT,    "?"),
    }
    color, label = gait_map.get(gait or "", (_GEYSIRWEISS, "---"))

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.6, min(w, h) / 600.0)
    thick = max(1, int(scale * 2))
    (tw, th), _ = cv2.getTextSize(label, font, scale * 1.4, thick + 1)
    pad = 12
    cv2.rectangle(overlay, (pad, pad), (pad * 2 + tw, pad * 2 + th), _LAVAGESTEIN, -1)
    cv2.putText(overlay, label, (pad + pad // 2, pad + th + 4),
                font, scale * 1.4, color, thick + 1, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.88, frame, 0.12, 0)
