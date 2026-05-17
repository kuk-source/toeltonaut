from collections import deque
from dataclasses import dataclass

import numpy as np


def _angle(p1: tuple, vertex: tuple, p2: tuple) -> float:
    """2D-Gelenkwinkel am vertex zwischen p1-vertex und vertex-p2 (Grad, 0–180).
    Akzeptiert (x,y) und (x,y,conf) – nur erste zwei Elemente werden genutzt."""
    v1 = np.array(p1[:2], dtype=float) - np.array(vertex[:2], dtype=float)
    v2 = np.array(p2[:2], dtype=float) - np.array(vertex[:2], dtype=float)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 180.0
    return float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))))


def _find_peaks(arr: np.ndarray, min_prominence: float = 0.02) -> list[int]:
    """Lokale Maxima via Savitzky-Golay-Glättung + scipy find_peaks mit Prominenz-Filter."""
    from scipy.signal import find_peaks as _scipy_peaks, savgol_filter as _savgol
    if len(arr) < 7:
        return []
    win = min(7, len(arr) if len(arr) % 2 == 1 else len(arr) - 1)
    if win < 3:
        return []
    smooth = _savgol(arr, window_length=win, polyorder=min(3, win - 1))
    peaks, _ = _scipy_peaks(smooth, prominence=min_prominence, distance=3)
    return peaks.tolist()


def _find_foot_on_events(
    y_rel_seq: np.ndarray,
    ground_y: float,
    threshold: float = 0.05,
    min_stance_frames: int = 3,
) -> list[int]:
    """Erkennt Foot-On-Ereignisse basierend auf Bodenlinie.

    Ein Foot-On tritt auf wenn y_rel >= ground_y - threshold (Huf nahe am Boden).
    Foot-Off: erste Frame nach einem Foot-On wo y_rel < ground_y - threshold.
    Rückgabe: Frame-Indizes der Foot-On-Ereignisse (erster Frame jeder Standphase).

    min_stance_frames verhindert Rausch-Ereignisse: eine Standphase muss mindestens
    so viele aufeinanderfolgende Frames enthalten.
    """
    if len(y_rel_seq) == 0 or ground_y < 0.1:
        return []

    on_threshold = ground_y - threshold
    events: list[int] = []
    in_stance = False
    stance_start = 0
    stance_len = 0

    for idx, y in enumerate(y_rel_seq):
        if y >= on_threshold:
            if not in_stance:
                in_stance = True
                stance_start = idx
                stance_len = 1
            else:
                stance_len += 1
        else:
            if in_stance:
                if stance_len >= min_stance_frames:
                    events.append(stance_start)
                in_stance = False
                stance_len = 0

    # Offene Standphase am Ende berücksichtigen
    if in_stance and stance_len >= min_stance_frames:
        events.append(stance_start)

    return events


def _smooth(a: np.ndarray, window: int = 5) -> np.ndarray:
    """Gleitender Mittelwert (mode='same'); bei zu kurzer Trajektorie unverändert."""
    if len(a) < window:
        return a
    return np.convolve(a, np.ones(window) / window, mode="same")


def _clean_trajectory(arr: np.ndarray, max_jump: float = 0.05, max_gap: int = 5) -> np.ndarray:
    """Displacement-Filterung + Cubic-Spline-Interpolation für Keypoint-Trajektorien.

    max_jump: Maximaler erlaubter Frame-zu-Frame-Sprung (normiert, bbox-relativ).
              > 5% bbox-Höhe in einem Frame = MMPose-Fehldetektion → als NaN markieren.
    max_gap:  Maximale Lückenlänge für Interpolation. Längere Lücken bleiben NaN.
    """
    if len(arr) < 3:
        return arr
    cleaned = arr.astype(float).copy()
    # Displacement-Filter: sprunghafte Änderungen als NaN markieren
    diffs = np.abs(np.diff(cleaned))
    for i, d in enumerate(diffs):
        if d > max_jump:
            cleaned[i + 1] = np.nan
    # Kurze NaN-Lücken (≤ max_gap) per Cubic-Spline interpolieren
    nan_mask = np.isnan(cleaned)
    if not nan_mask.any():
        return cleaned
    x_valid = np.where(~nan_mask)[0]
    if len(x_valid) < 4:  # Zu wenig Punkte für Cubic-Spline
        # Linearer Fallback
        cleaned = np.interp(
            np.arange(len(cleaned)), x_valid, cleaned[x_valid]
        )
        return cleaned
    from scipy.interpolate import CubicSpline
    cs = CubicSpline(x_valid, cleaned[x_valid])
    x_all = np.arange(len(cleaned))
    interpolated = cs(x_all)
    # Nur Lücken ≤ max_gap füllen
    nan_indices = np.where(nan_mask)[0]
    # Lücken segmentieren
    if len(nan_indices) > 0:
        gaps = np.split(nan_indices, np.where(np.diff(nan_indices) != 1)[0] + 1)
        for gap in gaps:
            if len(gap) <= max_gap:
                cleaned[gap] = interpolated[gap]
            # Längere Lücken: mit Nachbarwerten auffüllen (forward-fill)
            else:
                for idx in gap:
                    prev = idx - 1
                    while prev >= 0 and np.isnan(cleaned[prev]):
                        prev -= 1
                    if prev >= 0:
                        cleaned[idx] = cleaned[prev]
    return cleaned


@dataclass
class GaitResult:
    name: str
    confidence: float
    note: str = ""
    speed_ms: float | None = None


class GaitDetector:
    """Regelbasierte Gangart-Erkennung aus Fesselgelenk-Positionen, Bbox-Bewegung und Gelenk-Winkeln.

    Korrekte biomechanische Metriken (algo.odt):
      LAP  = Lateral Advanced Placement: zeitlicher Versatz LH→LF / T_stride (%)
      DF   = Duty Factor: Standphasenanteil pro Schrittzyklus (%)

    Ground-Truth-Matrix:
      Schritt : LAP ~25%, DF 60–70%, keine Schwebephase
      Trab    : LAP ~50%, DF 30–55%, Schwebephase
      Galopp  : LAP N/A,  DF 20–30%, Schwebephase
      Tölt    : LAP ~25%, DF 30–55%, keine Schwebephase (LAP<22%→passig, >28%→trabig)
      Rennpass: LAP ~0%,  DF <30%,   Schwebephase

    v0.1: Bbox-Bewegungs-Heuristik (proportionale KP liefern keine LAP-fähigen Trajektorien)
    v0.2+: LAP+DF aus echten ML-Keypoint-Trajektorien + Winkel-Features als Backup
    """

    WINDOW = 30
    MIN_FRAMES = 10

    # v0.1 PropPoseEstimator KP-Indizes (31 KP Schema)
    _DEFAULT_FETLOCK = {"l_front": 12, "r_front": 13, "l_hind": 14, "r_hind": 15, "withers": 6}

    # Sprint G1: Foot-On-Erkennungs-Parameter
    GROUND_THRESHOLD = 0.08   # Abstand zur Bodenlinie für Foot-On (bbox-relativ)
    MIN_STANCE_FRAMES = 3     # Mindest-Standphasen-Länge gegen Rauschen

    def __init__(
        self,
        fps: float = 30.0,
        vid_stride: int = 2,
        fetlock_indices: dict[str, int] | None = None,
        smooth_window: int = 5,
        conf_threshold: float = 0.3,
        stockmass_cm: int | None = None,
    ) -> None:
        self.effective_fps = fps / vid_stride
        self.smooth_window = smooth_window
        self.conf_threshold = conf_threshold
        self.stockmass_m: float | None = stockmass_cm / 100.0 if stockmass_cm is not None else None
        fi = fetlock_indices or self._DEFAULT_FETLOCK
        self._idx_lf      = fi.get("l_front",  12)
        self._idx_rf      = fi.get("r_front",  13)
        self._idx_lh      = fi.get("l_hind",   14)
        self._idx_rh      = fi.get("r_hind",   15)
        self._idx_withers = fi.get("withers",   6)
        self._idx_hock_l  = fi.get("l_hock",  None)
        self._idx_hock_r  = fi.get("r_hock",  None)
        self._idx_stifle  = fi.get("stifle",  None)
        self._idx_carp_l  = fi.get("l_carpus", None)
        self._idx_carp_r  = fi.get("r_carpus", None)
        self._idx_elbow   = fi.get("elbow",   None)
        # Fesselgelenk Y normiert (bbox-relativ: 0=oben, 1=unten/Boden)
        self._lf: deque[float] = deque(maxlen=self.WINDOW)
        self._rf: deque[float] = deque(maxlen=self.WINDOW)
        self._lh: deque[float] = deque(maxlen=self.WINDOW)
        self._rh: deque[float] = deque(maxlen=self.WINDOW)
        self._bbox_h: deque[float] = deque(maxlen=self.WINDOW)
        self._is_side_view: deque[bool] = deque(maxlen=self.WINDOW)
        # Bbox-Bewegungsfeatures (v0.1)
        self._bbox_cx: deque[float] = deque(maxlen=self.WINDOW)
        self._bbox_cy: deque[float] = deque(maxlen=self.WINDOW)
        # Geschwindigkeits-Trajektorie: cx, bbox_h und bg_flow synchron für linreg (~2 s Fenster)
        # Alle drei immer zusammen befüllt (nur is_side_view-Frames) → Index-Synchronität garantiert
        _traj_size = max(10, int(self.effective_fps * 2))
        self._traj_cx: deque[float] = deque(maxlen=_traj_size)
        self._traj_h: deque[float] = deque(maxlen=_traj_size)
        # Kameraschwenk-Korrektur: medianer Hintergrund-Optical-Flow (px/Frame)
        # Positiv = Hintergrund nach rechts = Kamera schwenkt nach links
        self._traj_bg_flow: deque[float] = deque(maxlen=_traj_size)
        # Gelenkwinkel (v0.2)
        self._hock_l: deque[float] = deque(maxlen=self.WINDOW)
        self._hock_r: deque[float] = deque(maxlen=self.WINDOW)
        self._carpus_l: deque[float] = deque(maxlen=self.WINDOW)
        self._carpus_r: deque[float] = deque(maxlen=self.WINDOW)
        # Topline (v0.2)
        self._withers_y: deque[float] = deque(maxlen=self.WINDOW)
        self._croup_y: deque[float] = deque(maxlen=self.WINDOW)
        # Sprunggelenk-Y (B3 Phase 2): ergänzt DF-Berechnung
        self._hock_l_y: deque[float] = deque(maxlen=self.WINDOW)
        self._hock_r_y: deque[float] = deque(maxlen=self.WINDOW)
        # Sprint G1: Rolling-Minimum-Buffer pro Bein für dynamische Bodenlinie
        # Fenster ~2 Sekunden = effective_fps * 2; mind. 1 Frame
        rolling_window = max(1, int(self.effective_fps * 2))
        self._ground_buf_lf: deque[float] = deque(maxlen=rolling_window)
        self._ground_buf_rf: deque[float] = deque(maxlen=rolling_window)
        self._ground_buf_lh: deque[float] = deque(maxlen=rolling_window)
        self._ground_buf_rh: deque[float] = deque(maxlen=rolling_window)
        # LH Fesselgelenk X-Position (absolute Pixel) für Stride-Length-Berechnung
        # Immer synchron mit _lh befüllt → gleiche Indexierung garantiert
        self._lh_x: deque[float] = deque(maxlen=self.WINDOW)
        # Kameraschwenk-Korrektur für Stride-Methode: bg_flow synchron zu _lh_x
        self._lh_bg_flow: deque[float] = deque(maxlen=self.WINDOW)
        # Foot-On-Peak-Cache: von _compute_lap_df gesetzt, von _compute_speed_stride gelesen
        self._cached_lh_peaks: list[int] = []
        self._frame_count = 0

    def _kp_y(self, keypoints: list[tuple], idx: int, y1: int, h: int) -> float | None:
        """Normierte Y-Koordinate eines Keypoints; None wenn Index fehlt oder Konfidenz < Threshold."""
        if idx >= len(keypoints):
            return None
        kp = keypoints[idx]
        if len(kp) > 2 and float(kp[2]) < self.conf_threshold:
            return None
        return (int(kp[1]) - y1) / h

    def update(
        self,
        keypoints: list[tuple],
        bbox: tuple[int, int, int, int],
        is_side_view: bool = True,
        bg_flow_px: float = 0.0,
    ) -> None:
        x1, y1, x2, y2 = bbox
        h = max(1, y2 - y1)
        self._is_side_view.append(is_side_view)
        if is_side_view:
            for deq, ground_buf, idx, x_deq in [
                (self._lf, self._ground_buf_lf, self._idx_lf, None),
                (self._rf, self._ground_buf_rf, self._idx_rf, None),
                (self._lh, self._ground_buf_lh, self._idx_lh, self._lh_x),
                (self._rh, self._ground_buf_rh, self._idx_rh, None),
            ]:
                val = self._kp_y(keypoints, idx, y1, h)
                if val is not None:
                    deq.append(val)
                    # Sprint G1: rolling-maximum der bbox-relativen Y-Werte als Bodenlinie
                    # (maximum weil y_rel=1.0 = Boden; Maximum der letzten ~2s = tiefster Punkt)
                    ground_buf.append(val)
                    if x_deq is not None:
                        x_deq.append(float(keypoints[idx][0]))
                        self._lh_bg_flow.append(bg_flow_px)
            if self._idx_hock_l is not None:
                val = self._kp_y(keypoints, self._idx_hock_l, y1, h)
                if val is not None:
                    self._hock_l_y.append(val)
            if self._idx_hock_r is not None:
                val = self._kp_y(keypoints, self._idx_hock_r, y1, h)
                if val is not None:
                    self._hock_r_y.append(val)
        self._bbox_h.append(float(h))
        bbox_cx = float(x1 + x2) / 2.0
        self._bbox_cx.append(bbox_cx)
        self._bbox_cy.append(float(y1 + y2) / 2.0)
        # Geschwindigkeits-Trajektorie: cx + h + bg_flow synchron (nur Seitenansicht, Bbox stabil)
        # Alle drei immer im gleichen Frame befüllt → Index-Synchronität garantiert
        if is_side_view and h > 10:
            self._traj_cx.append(bbox_cx)
            self._traj_h.append(float(h))
            self._traj_bg_flow.append(bg_flow_px)
        # Sprunggelenk-Winkel: Stifle – Hock – Fetlock (Horse-10: 17–13–14 / 17–18–19)
        if (self._idx_hock_l is not None and self._idx_stifle is not None
                and len(keypoints) > max(self._idx_hock_l, self._idx_stifle, self._idx_lh)):
            self._hock_l.append(_angle(
                keypoints[self._idx_stifle],
                keypoints[self._idx_hock_l],
                keypoints[self._idx_lh],
            ))
        if (self._idx_hock_r is not None and self._idx_stifle is not None
                and len(keypoints) > max(self._idx_hock_r, self._idx_stifle, self._idx_rh)):
            self._hock_r.append(_angle(
                keypoints[self._idx_stifle],
                keypoints[self._idx_hock_r],
                keypoints[self._idx_rh],
            ))
        # Karpalwinkel: Elbow – Carpus – Fetlock (Horse-10: 10–2–3 / 10–5–6)
        if (self._idx_carp_l is not None and self._idx_elbow is not None
                and len(keypoints) > max(self._idx_carp_l, self._idx_elbow, self._idx_lf)):
            self._carpus_l.append(_angle(
                keypoints[self._idx_elbow],
                keypoints[self._idx_carp_l],
                keypoints[self._idx_lf],
            ))
        if (self._idx_carp_r is not None and self._idx_elbow is not None
                and len(keypoints) > max(self._idx_carp_r, self._idx_elbow, self._idx_rf)):
            self._carpus_r.append(_angle(
                keypoints[self._idx_elbow],
                keypoints[self._idx_carp_r],
                keypoints[self._idx_rf],
            ))
        # Topline
        if len(keypoints) > self._idx_withers:
            self._withers_y.append((keypoints[self._idx_withers][1] - y1) / h)
        # Kruppe: v0.1 Index 30, Horse-10 Ischium Index 21 (nächster Proxy)
        _croup_idx = 21 if len(keypoints) <= 22 else 30
        if len(keypoints) > _croup_idx:
            self._croup_y.append((keypoints[_croup_idx][1] - y1) / h)
        self._frame_count += 1

    # ── LAP / DF – Kernalgorithmus (v0.2) ──────────────────────────────────

    def _ground_y(self, ground_buf: deque) -> float | None:
        """Dynamische Bodenlinie: Maximum der bbox-relativen Y-Werte im Rolling-Window.

        Gibt None zurück wenn der Buffer leer ist.
        Liegt die Bodenlinie unter 0.3 (zu hoch im Bild), wird None zurückgegeben –
        die Bbox-relative Methode ist dann unzuverlässig (z.B. kein Bodenkontakt im Clip).
        """
        if not ground_buf:
            return None
        g = float(max(ground_buf))
        if g < 0.3:
            return None
        if g < 0.92:  # Huf erreicht nie den unteren Bbox-Rand → Bodenlinie unzuverlässig
            return None
        return g

    def _compute_lap_df(self) -> tuple[float, float] | None:
        """Berechnet LAP (Lateral Advanced Placement) und mittleren Duty Factor.

        LAP = (t_FO_LF − t_FO_LH) / T_stride  [0..1]
        DF  = Standphasenanteil pro Schrittzyklus, gemittelt über alle 4 Beine

        Sprint G1: Foot-On-Erkennung über dynamische Bodenlinie (bbox-relatives rolling maximum)
        statt roher Trajektorie-Peaks. Fallback auf Peak-basierte Methode wenn keine
        Bbox-Daten verfügbar (ground_y = None für alle Beine).

        Gibt None zurück wenn zu wenig Foot-On-Events oder Stridevarianz zu hoch.
        """
        lh = np.array(self._lh)
        lf = np.array(self._lf)
        rh = np.array(self._rh)
        rf = np.array(self._rf)

        if len(lh) < self.MIN_FRAMES:
            return None

        # refineDLC-Pipeline: Displacement-Filter + Spline-Interpolation vor Peak-Detektion
        lh = _clean_trajectory(lh)
        lf = _clean_trajectory(lf)
        rh = _clean_trajectory(rh)
        rf = _clean_trajectory(rf)

        # Adaptive Fensterkorrektur: Wenn Stride-Periode aus FFT schätzbar, prüfen ob
        # aktuelles Fenster mindestens 2 Stride-Zyklen enthält
        if len(lh) >= 16:
            fft_mag = np.abs(np.fft.rfft(lh - np.mean(lh)))
            freqs = np.fft.rfftfreq(len(lh))
            dominant_idx = int(np.argmax(fft_mag[1:]) + 1)  # DC-Anteil überspringen
            if dominant_idx > 0 and freqs[dominant_idx] > 0:
                estimated_stride_frames = int(round(1.0 / freqs[dominant_idx]))
                # Nur als Info nutzen; Fensteranpassung geschieht über WINDOW-Parameter
                # Wenn Stride-Periode > WINDOW/2, ist Klassifikation unzuverlässig → None
                if estimated_stride_frames > len(lh) * 0.6:
                    return None  # Fenster zu klein für zuverlässige LAP-Berechnung

        lh_s = _smooth(lh, self.smooth_window)
        lf_s = _smooth(lf, self.smooth_window)
        rh_s = _smooth(rh, self.smooth_window)
        rf_s = _smooth(rf, self.smooth_window)

        # Sprint G1: Bodenlinie pro Bein berechnen
        g_lh = self._ground_y(self._ground_buf_lh)
        g_lf = self._ground_y(self._ground_buf_lf)
        g_rh = self._ground_y(self._ground_buf_rh)
        g_rf = self._ground_y(self._ground_buf_rf)

        use_ground_line = g_lh is not None and g_lf is not None

        if use_ground_line:
            # G1-Pfad: Bodenlinie-basierte Foot-On-Erkennung
            lh_peaks = _find_foot_on_events(
                lh_s, g_lh, self.GROUND_THRESHOLD, self.MIN_STANCE_FRAMES
            )
            lf_peaks = _find_foot_on_events(
                lf_s, g_lf, self.GROUND_THRESHOLD, self.MIN_STANCE_FRAMES
            )
            rh_peaks = _find_foot_on_events(
                rh_s, g_rh if g_rh is not None else g_lh,
                self.GROUND_THRESHOLD, self.MIN_STANCE_FRAMES
            )
            rf_peaks = _find_foot_on_events(
                rf_s, g_rf if g_rf is not None else g_lf,
                self.GROUND_THRESHOLD, self.MIN_STANCE_FRAMES
            )
        else:
            # Fallback: Peak-basierte Methode (keine bbox-Daten)
            lh_peaks = _find_peaks(lh_s)
            lf_peaks = _find_peaks(lf_s)
            rh_peaks = _find_peaks(rh_s)
            rf_peaks = _find_peaks(rf_s)

        self._cached_lh_peaks = lh_peaks
        if len(lh_peaks) < 2:
            return None

        # Stride Duration aus aufeinanderfolgenden LH Foot-On Events
        strides = [lh_peaks[i + 1] - lh_peaks[i] for i in range(len(lh_peaks) - 1)]
        T = float(np.median(strides))
        if T < 4 or T > self.WINDOW * 0.9:
            return None

        # LAP: Phasenversatz LF relativ zu LH innerhalb eines Schrittzyklus
        lap_values: list[float] = []
        for lh_fo in lh_peaks[:-1]:
            candidates = [p for p in lf_peaks if 0 < (p - lh_fo) < T]
            if candidates:
                dt = min(candidates, key=lambda p: abs(p - lh_fo - T * 0.25)) - lh_fo
                lap_values.append(float(dt) / T)

        if not lap_values:
            return None
        lap = float(np.median(lap_values))
        # LAP ∈ [0,1]; Rennpass (LAP≈0) kann auch als LAP≈1 auftauchen → wrappen
        if lap > 0.75:
            lap = 1.0 - lap

        # DF: Perzentil-basiert – NUR Fesselgelenke (berühren den Boden).
        # Sprunggelenke/Karpus NICHT einbeziehen: diese Gelenke berühren nie den Boden,
        # ihr Y-Wert ist dauerhaft hoch und würde DF systematisch überschätzen → Tölt → Schritt.
        df_values = []
        for arr in [lh_s, lf_s, rh_s, rf_s]:
            if len(arr) < self.MIN_FRAMES:
                continue
            p_low  = float(np.percentile(arr, 15))
            p_high = float(np.percentile(arr, 90))
            rng = p_high - p_low
            if rng < 0.04:  # Zu geringe Varianz → kein Stance/Swing-Muster erkennbar
                continue
            thr = p_low + 0.55 * rng
            df_values.append(float(np.mean(arr >= thr)))
        df = float(np.mean(df_values)) if df_values else 0.5

        return lap, df

    # ── Geschwindigkeitsschätzung (Sprint G3) ──────────────────────────────

    def _compute_speed_stride(self, gait: str = "---") -> float | None:
        """Geschwindigkeit aus Schrittlänge × Schrittfrequenz: v = L / T.

        Schrittlänge L = medianer Pixel-X-Abstand des LH-Fesselgelenks zwischen
        aufeinanderfolgenden Foot-On-Events, skaliert mit Bbox-Höhe / Stockmaß.
        Robust gegen Bbox-Jitter und Kameraschwenk im Stand; nutzt bereits
        berechnete lh_peaks aus _compute_lap_df().
        """
        peaks = self._cached_lh_peaks
        if len(peaks) < 2 or self.stockmass_m is None:
            return None
        lh_x = np.array(self._lh_x)
        bh   = np.array(self._bbox_h)
        # _lh_x und _lh werden synchron befüllt; Länge muss peaks abdecken
        if len(lh_x) < max(peaks) + 1:
            return None

        # Kameraschwenk-Korrektur für Stride-Methode
        # _lh_bg_flow ist synchron zu _lh_x → gleiche Indexierung
        bg_arr = np.array(self._lh_bg_flow)
        has_bg = len(bg_arr) == len(lh_x)

        stride_px: list[float] = []
        stride_durations: list[float] = []
        for i in range(len(peaks) - 1):
            p0, p1 = peaks[i], peaks[i + 1]
            raw_dx = lh_x[p1] - lh_x[p0]
            if has_bg and p1 < len(bg_arr):
                # Kumulierter Kameraschwenk über diese Stride-Dauer
                # lh_x ist Rohpixel im Frame; Weltbewegung = raw_dx − cumsum(bg_flow über Stride)
                # Vorzeichen: bg_flow > 0 → Hintergrund nach rechts → Kamera links → Korrektur −
                cum_bg_stride = float(np.sum(bg_arr[p0:p1]))
                corrected_dx = raw_dx - cum_bg_stride
            else:
                corrected_dx = raw_dx
            # Stride > 3× Pferd-Höhe = Keypoint-Ausreißer (MMPose-Fehldetektion) → verwerfen
            local_bh = float(np.median(bh[p0 : p1 + 1])) if p1 < len(bh) else 0.0
            if local_bh > 0 and abs(corrected_dx) > local_bh * 3.0:
                continue
            stride_px.append(abs(corrected_dx))
            stride_durations.append((p1 - p0) / self.effective_fps)

        if not stride_px:
            return None
        median_stride_px = float(np.median(stride_px))
        if median_stride_px < 5:  # < 5 px = kaum Vorwärtsbewegung (Kameraschwenk o.ä.)
            return None

        median_bh = float(np.median(bh))
        if median_bh < 10:
            return None

        stride_length_m = median_stride_px / (median_bh / self.stockmass_m)

        median_stride_s = float(np.median(stride_durations))
        if median_stride_s < 0.15:  # < 0.15 s Schrittdauer = physikalisch unmöglich
            return None

        speed = stride_length_m / median_stride_s
        upper = self._GAIT_SPEED_MAX_MS.get(gait, 17.0)
        if speed < 0.3 or speed > upper:
            return None
        return round(speed, 2)

    # Obere Geschwindigkeitsgrenze pro Gangart (m/s), großzügig aber physikalisch
    _GAIT_SPEED_MAX_MS: dict[str, float] = {
        "Schritt":  3.0,   # ~10,8 km/h
        "Tölt":    10.0,   # ~36 km/h (inkl. sehr schneller Wettkampf-Tölt)
        "Trab":     8.0,   # ~28,8 km/h
        "Galopp":  12.0,   # ~43 km/h
        "Rennpass": 17.0,  # ~61 km/h
    }

    def _compute_speed(self, gait: str = "---") -> float | None:
        """Schätzt Pferd-Geschwindigkeit in m/s.

        Primär: _compute_speed_stride() – Schrittlänge × Schrittfrequenz (v = L / T).
        Fallback: Lineare Regression über cx-Trajektorie (px/Frame → m/s).

        Sanity-Grenzen: global 0,3–17 m/s + gangart-spezifische Obergrenzen.
        """
        # Primärmethode: Stride-Length (nur wenn Peaks aus _compute_lap_df verfügbar)
        if len(self._cached_lh_peaks) >= 2:
            stride_speed = self._compute_speed_stride(gait)
            if stride_speed is not None:
                return stride_speed

        # Fallback: Lineare Regression über cx-Trajektorie
        cx = np.array(self._traj_cx)
        bh = np.array(self._traj_h)

        # Mindest-Datenpunkte: ~0,5 s bei effective_fps
        min_pts = max(6, int(self.effective_fps * 0.5))
        if len(cx) < min_pts or len(bh) < min_pts:
            return None

        # Kameraschwenk-Korrektur: Kumulativer Hintergrundfluss aus cx rausrechnen
        # Wenn Kamera nach rechts schwenkt → bg_flow < 0 → Hintergrund geht nach links
        # → Pferd erscheint im Frame links zu gehen, ist aber in der Welt rechts
        # → cx_welt = cx_frame − cumsum(bg_flow)
        bg = np.array(self._traj_bg_flow)
        if len(bg) == len(cx) and len(bg) > 0:
            cum_bg = np.cumsum(bg)
            cx_corrected = cx - cum_bg
        else:
            cx_corrected = cx

        n = len(cx_corrected)
        t = np.arange(n, dtype=float)

        # Linearer Trend: cx(t) = slope * t + intercept
        slope, intercept = np.polyfit(t, cx_corrected, 1)    # px / frame
        speed_px_per_s = abs(slope) * self.effective_fps   # px / s

        # Pixelmaßstab aus medianer Bbox-Höhe
        median_h = float(np.median(bh))
        if median_h < 10:
            return None

        if self.stockmass_m is not None:
            px_per_m = median_h / self.stockmass_m
            speed = speed_px_per_s / px_per_m
        else:
            # Kein Stockmaß: normierte Größe zurückgeben (px/s / px → s⁻¹, nicht m/s)
            # → None liefern, damit kein falscher m/s-Wert angezeigt wird
            return None

        # Sanity-Check: global 0,3–17 m/s + gangart-spezifische Obergrenze
        upper = self._GAIT_SPEED_MAX_MS.get(gait, 17.0)
        if speed < 0.3 or speed > upper:
            return None

        # Plausibilitäts-Filter: r² der Regression muss ausreichend sein (> 0,10)
        # → schlechte Regression (Pferd steht, dreht, unklar) wird verworfen
        cx_fit = slope * t + intercept
        ss_res = float(np.sum((cx_corrected - cx_fit) ** 2))
        ss_tot = float(np.sum((cx_corrected - np.mean(cx_corrected)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0
        if r2 < 0.10:
            return None

        return round(speed, 2)

    # ── Klassifikation ──────────────────────────────────────────────────────

    def detect(self) -> GaitResult:
        """Erkennt Gangart und fügt Geschwindigkeitsschätzung (speed_ms) hinzu."""
        result = self._detect_gait()
        result.speed_ms = self._compute_speed(result.name)
        return result

    def _detect_gait(self) -> GaitResult:
        if self._frame_count < self.MIN_FRAMES:
            return GaitResult("---", 0.0, "Zu wenig Frames")

        lf = np.array(self._lf)
        rf = np.array(self._rf)
        lh = np.array(self._lh)
        rh = np.array(self._rh)

        mean_var = float(np.mean([np.var(lf), np.var(rf), np.var(lh), np.var(rh)]))

        # ── Pfad A: Echte ML-Keypoints (v0.2+) ─────────────────────────────
        # mean_var > 0 weil Fesselgelenke tatsächlich variieren
        if mean_var > 0.0003:
            # Primär: LAP + DF (biomechanisch korrekte Metriken, algo.odt)
            lap_df = self._compute_lap_df()
            if lap_df is not None:
                lap, df = lap_df
                note_base = f"LAP={lap:.2f} DF={df:.2f}"

                # Entscheidungsbaum nach Hildebrand-Diagramm / biomechanischer Literatur:
                # Trab: LAP≈50%, Schwebephase vorhanden (DF<50%)
                if 0.40 <= lap <= 0.60 and df < 0.55:
                    return GaitResult("Trab", min(0.85, 1.0 - abs(lap - 0.50) * 5),
                                      f"{note_base} – diagonales Zweitakt-Muster")

                # Rennpass: LAP≈0% (simultan lateral), Schwebephase (DF<30%)
                if lap < 0.10 and df < 0.35:
                    return GaitResult("Rennpass", 0.80,
                                      f"{note_base} – laterale Synchronizität + Schwebephase")

                # Schritt: LAP≈25%, sehr hoher DF (lange Stützphase, 3-4 Beine am Boden)
                if 0.15 <= lap <= 0.35 and df >= 0.60:
                    return GaitResult("Schritt", 0.78,
                                      f"{note_base} – hoher Stützphasenanteil (3-4-Bein-Support)")

                # Tölt: LAP≈25%, mittlerer DF (uni-/bipedaler Support, keine Schwebephase)
                if 0.15 <= lap <= 0.35 and df < 0.60:
                    # FEIF-Subklassifikation: passiger Tölt, korrekter Tölt, trabiger Tölt
                    if lap < 0.22:
                        sub = "PASSIGER Tölt – LAP zu niedrig (<22%)"
                    elif lap > 0.28:
                        sub = "TRABIGER Tölt – LAP zu hoch (>28%)"
                    else:
                        sub = "korrektes laterales Viergang-Muster"
                    conf = 0.88 if 0.22 <= lap <= 0.28 else 0.72
                    return GaitResult("Tölt", conf, f"{note_base} – {sub}")

                # Galopp: asymmetrisch, hohe Dynamik, kurze Standphasen
                if df < 0.35:
                    return GaitResult("Galopp", 0.62,
                                      f"{note_base} – gesprungene asymmetrische Gangart")

            # Fallback: Korrelations-Features (wenn LAP-Berechnung scheitert)
            def safe_corr(a: np.ndarray, b: np.ndarray) -> float:
                n = min(len(a), len(b))
                if n < 3:
                    return 0.0
                a, b = a[-n:], b[-n:]
                if np.var(a) < 1e-9 or np.var(b) < 1e-9:
                    return 0.0
                c = np.corrcoef(a, b)
                return float(c[0, 1]) if not np.isnan(c[0, 1]) else 0.0

            lat_sync = (abs(safe_corr(lf, lh)) + abs(safe_corr(rf, rh))) / 2.0
            diag_sync = (abs(safe_corr(lf, rh)) + abs(safe_corr(rf, lh))) / 2.0

            topline_smooth = 1.0
            if len(self._withers_y) >= self.MIN_FRAMES:
                wy = np.array(self._withers_y)
                topline_smooth = 1.0 - min(float(np.var(wy)) / 0.005, 1.0)

            carpus_var = 0.0
            if len(self._carpus_l) >= self.MIN_FRAMES:
                cl = np.array(self._carpus_l)
                cr = np.array(self._carpus_r)
                carpus_var = float(np.mean([np.var(cl), np.var(cr)]))

            if lat_sync > 0.65 and diag_sync < 0.40:
                if mean_var > 0.012:
                    return GaitResult("Rennpass", min(lat_sync, 0.80),
                                      "Laterale Synchronität + hohe Dynamik")
                conf = min(lat_sync, 0.85)
                if topline_smooth > 0.7:
                    conf = min(conf + 0.04, 0.90)
                if carpus_var > 80:
                    conf = min(conf + 0.03, 0.90)
                return GaitResult("Tölt", conf, "Laterales Muster + Topline-Analyse (Korrelations-Fallback)")
            if diag_sync > 0.60 and lat_sync < 0.40:
                return GaitResult("Trab", min(diag_sync, 0.85),
                                  "Diagonales Muster erkannt (Korrelations-Fallback)")
            if mean_var > 0.008:
                return GaitResult("Galopp", 0.52, "Hohe Bewegungsdynamik")
            if mean_var < 0.003:
                return GaitResult("Schritt", 0.58, "Gleichmäßige Bewegung")
            return GaitResult("Unbekannt", 0.28, "Muster nicht eindeutig")

        # ── Pfad B: Proportionale Keypoints (v0.1) ─────────────────────────
        # Fesselgelenk-Y ist konstant ~0.87 → LAP/DF nicht berechenbar.
        # Bbox-Bewegungs-Heuristik als einzige praktikable Methode.
        bbox_arr = np.array(self._bbox_h)
        bbox_speed = 0.0
        bbox_bounce = 0.0
        if len(self._bbox_cx) >= 3:
            cx_arr = np.array(self._bbox_cx)
            bbox_speed = float(np.mean(np.abs(np.diff(cx_arr))) / (np.mean(bbox_arr) + 1e-9))
        if len(self._bbox_cy) >= 3:
            cy_arr = np.array(self._bbox_cy)
            bbox_bounce = float(np.var(cy_arr) / (np.mean(bbox_arr) ** 2 + 1e-9))

        if bbox_speed < 0.005 and bbox_bounce < 0.0005:
            return GaitResult("Schritt", 0.45, "Geringe Bewegung (v0.1)")
        if bbox_speed > 0.060:
            if bbox_bounce > 0.0015:
                return GaitResult("Galopp", 0.42, "Hohe Dynamik erkannt (v0.1)")
            return GaitResult("Rennpass", 0.38, "Hohe Geschwindigkeit erkannt (v0.1)")
        if bbox_bounce > 0.0012:
            return GaitResult("Trab", 0.42, "Vertikale Bewegung erkannt (v0.1)")
        if bbox_speed > 0.015:
            return GaitResult("Tölt", 0.42, "Gleichmäßige Vorwärtsbewegung (v0.1)")
        return GaitResult("Schritt", 0.38, "Geringe Dynamik (v0.1 – proportionale KP)")
