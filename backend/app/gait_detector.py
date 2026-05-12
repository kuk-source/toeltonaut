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


def _find_peaks(arr: np.ndarray, min_prominence: float = 0.01) -> list[int]:
    """Lokale Maxima in arr mit Mindest-Prominenz (kein scipy nötig)."""
    peaks = []
    for i in range(1, len(arr) - 1):
        if arr[i] >= arr[i - 1] and arr[i] > arr[i + 1]:
            left_min = float(np.min(arr[max(0, i - 6):i]))
            right_min = float(np.min(arr[i + 1:min(len(arr), i + 7)]))
            if (arr[i] - left_min) >= min_prominence and (arr[i] - right_min) >= min_prominence:
                peaks.append(i)
    return peaks


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
    GROUND_THRESHOLD = 0.05   # Abstand zur Bodenlinie für Foot-On (bbox-relativ)
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
        # Sprint G3: normierte Δx/h-Werte für Geschwindigkeitsschätzung (~1 s Fenster)
        _speed_buf_size = max(1, int(self.effective_fps))
        self._speed_dx_norm: deque[float] = deque(maxlen=_speed_buf_size)
        # Geschwindigkeits-Trajektorie: cx und bbox_h synchron für linreg (~2 s Fenster)
        # Beide immer zusammen befüllt (nur is_side_view-Frames) → Index-Synchronität garantiert
        _traj_size = max(10, int(self.effective_fps * 2))
        self._traj_cx: deque[float] = deque(maxlen=_traj_size)
        self._traj_h: deque[float] = deque(maxlen=_traj_size)
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
    ) -> None:
        x1, y1, x2, y2 = bbox
        h = max(1, y2 - y1)
        self._is_side_view.append(is_side_view)
        if is_side_view:
            for deq, ground_buf, idx in [
                (self._lf, self._ground_buf_lf, self._idx_lf),
                (self._rf, self._ground_buf_rf, self._idx_rf),
                (self._lh, self._ground_buf_lh, self._idx_lh),
                (self._rh, self._ground_buf_rh, self._idx_rh),
            ]:
                val = self._kp_y(keypoints, idx, y1, h)
                if val is not None:
                    deq.append(val)
                    # Sprint G1: rolling-maximum der bbox-relativen Y-Werte als Bodenlinie
                    # (maximum weil y_rel=1.0 = Boden; Maximum der letzten ~2s = tiefster Punkt)
                    ground_buf.append(val)
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
        # Sprint G3: normiertes |Δx|/h für Geschwindigkeitsschätzung (nur Seitenansicht, stabile Bbox)
        if is_side_view and h > 10 and len(self._bbox_cx) >= 2:
            prev_cx = self._bbox_cx[-2]
            dx_norm = abs(bbox_cx - prev_cx) / h
            self._speed_dx_norm.append(dx_norm)
        # Geschwindigkeits-Trajektorie: cx + h synchron (nur Seitenansicht, Bbox stabil)
        # Beide immer im gleichen Frame befüllt → Index-Synchronität garantiert
        if is_side_view and h > 10:
            self._traj_cx.append(bbox_cx)
            self._traj_h.append(float(h))
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
        return g if g >= 0.3 else None

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

        # Duty Factor: Sprint G1 nutzt Bodenlinie-basierte Standphasen-Erkennung
        # B3 Phase 2: Sprunggelenk-Y ergänzt die 4 Fesselgelenk-Trajektorien (sofern vorhanden)
        df_values: list[float] = []
        if use_ground_line:
            # G1-Pfad: Standphase = y_rel >= ground_y - threshold
            for arr, g_y in [
                (lh_s, g_lh), (lf_s, g_lf),
                (rh_s, g_rh if g_rh is not None else g_lh),
                (rf_s, g_rf if g_rf is not None else g_lf),
            ]:
                on_thr = g_y - self.GROUND_THRESHOLD
                df_values.append(float(np.mean(arr >= on_thr)))
            # Sprunggelenk-Y (B3): Fallback auf alten Schwellenwert (kein ground_buf für Hocks)
            for hock_arr_src in [self._hock_l_y, self._hock_r_y]:
                if len(hock_arr_src) >= self.MIN_FRAMES:
                    arr = _smooth(np.array(hock_arr_src), self.smooth_window)
                    threshold = 0.95 * float(np.max(arr))
                    if threshold >= 0.5:
                        df_values.append(float(np.mean(arr >= threshold)))
        else:
            # Fallback: 95%-Schwellenwert wie bisher
            df_sources = [lh_s, lf_s, rh_s, rf_s]
            if len(self._hock_l_y) >= self.MIN_FRAMES:
                df_sources.append(_smooth(np.array(self._hock_l_y), self.smooth_window))
            if len(self._hock_r_y) >= self.MIN_FRAMES:
                df_sources.append(_smooth(np.array(self._hock_r_y), self.smooth_window))
            for arr in df_sources:
                threshold = 0.95 * float(np.max(arr))
                if threshold < 0.5:
                    continue
                df_values.append(float(np.mean(arr >= threshold)))
        df = float(np.mean(df_values)) if df_values else 0.5

        return lap, df

    # ── Geschwindigkeitsschätzung (Sprint G3) ──────────────────────────────

    def _compute_speed(self) -> float | None:
        """Schätzt Pferd-Geschwindigkeit in m/s via linearer Regression über cx-Trajektorie.

        Methode: linreg(frame_index → cx_px) liefert Anstieg in px/Frame.
        Skalierung: px/Frame × effective_fps × (stockmass_m / median_bbox_h) = m/s

        Vorteile gegenüber frame-by-frame Δx:
          - Robust gegen Bbox-Jitter (alle Frames gleichzeitig ausgewertet)
          - Kein Stride-Detektor nötig → funktioniert auch im v0.1-Modus
          - Vorzeichen zeigt Bewegungsrichtung (wird für Betrag genutzt)

        Fallback ohne Stockmaß: normierter Median |Δx|/h (nur Verhältnis, kein m/s).

        Sanity-Grenzen Islandpferd:
          Schritt 1,4–2,2 m/s | Tölt 3–9 | Trab 3,5–6 | Galopp 5–10 | Rennpass 10–16
          → Untergrenze 0,3 m/s (langsamer Schritt), Obergrenze 16,5 m/s (Rennpass-Spitze)
        """
        cx = np.array(self._traj_cx)
        bh = np.array(self._traj_h)

        # Mindest-Datenpunkte: ~0,5 s bei effective_fps
        min_pts = max(6, int(self.effective_fps * 0.5))
        if len(cx) < min_pts or len(bh) < min_pts:
            # Letzter Ausweg: einfacher normierter Δx-Median aus _speed_dx_norm
            if self.stockmass_m is None:
                return None
            buf = sorted(self._speed_dx_norm)
            if len(buf) < 6:
                return None
            active = buf[len(buf) // 2:]
            median_dx_norm = float(np.median(active))
            if median_dx_norm < 0.004:
                return None
            return round(median_dx_norm * self.stockmass_m * self.effective_fps, 2)

        n = len(cx)
        t = np.arange(n, dtype=float)

        # Linearer Trend: cx(t) = slope * t + intercept
        slope, intercept = np.polyfit(t, cx, 1)    # px / frame
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

        # Sanity-Check: Islandpferd 0,3–16,5 m/s
        if speed < 0.3 or speed > 16.5:
            return None

        # Plausibilitäts-Filter: r² der Regression muss ausreichend sein (> 0,10)
        # → schlechte Regression (Pferd steht, dreht, unklar) wird verworfen
        cx_fit = slope * t + intercept
        ss_res = float(np.sum((cx - cx_fit) ** 2))
        ss_tot = float(np.sum((cx - np.mean(cx)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0
        if r2 < 0.10:
            return None

        return round(speed, 2)

    # ── Klassifikation ──────────────────────────────────────────────────────

    def detect(self) -> GaitResult:
        """Erkennt Gangart und fügt Geschwindigkeitsschätzung (speed_ms) hinzu."""
        result = self._detect_gait()
        result.speed_ms = self._compute_speed()
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
