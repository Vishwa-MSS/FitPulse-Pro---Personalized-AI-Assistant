"""
breathing_engine.py
===================
Real-Time Breathing Rate Estimator for FitPulse Pro

Method: Tracks vertical oscillation of shoulder landmarks
        from MediaPipe pose data sent by the browser.
        Uses peak detection on the shoulder Y-signal to
        count breaths per minute (BPM).

No additional model needed — uses MediaPipe landmarks
already computed by the browser's existing pose estimator.
"""

import numpy as np
import time
from collections import deque
from scipy.signal import find_peaks, butter, filtfilt


# Normal BPM ranges
BPM_REST      = (12, 20)
BPM_EXERCISE  = (20, 35)
BPM_INTENSE   = (35, 60)


class BreathingEngine:
    """
    Estimates breathing rate (BPM) from MediaPipe shoulder landmark data.

    The browser sends shoulder Y-coordinates every ~100 ms.
    This class buffers the signal, band-pass filters it,
    detects peaks (inhalations), and computes BPM.
    """

    def __init__(self, sample_rate_hz: float = 10.0,
                 window_seconds: float = 20.0):
        """
        Args:
            sample_rate_hz:  How many samples/sec the browser sends (default ~10)
            window_seconds:  Signal window for analysis (default 20 s)
        """
        self.sample_rate   = sample_rate_hz
        self.window_size   = int(window_seconds * sample_rate_hz)
        self.signal_buffer = deque(maxlen=self.window_size)
        self.time_buffer   = deque(maxlen=self.window_size)
        self.bpm_history   = deque(maxlen=10)
        self.last_bpm      = 0.0
        self.last_update   = time.time()
        self.session_start = time.time()

        # For pattern message
        self.breath_events = []

    # ──────────────────────────────────────────────────────────────────────────
    # DATA INGESTION
    # ──────────────────────────────────────────────────────────────────────────
    def add_landmark(self, left_shoulder_y: float, right_shoulder_y: float):
        """
        Feed one sample from MediaPipe landmarks.

        Args:
            left_shoulder_y:  landmarks[11].y  (normalised 0-1)
            right_shoulder_y: landmarks[12].y  (normalised 0-1)
        """
        avg_y = (left_shoulder_y + right_shoulder_y) / 2.0
        self.signal_buffer.append(avg_y)
        self.time_buffer.append(time.time())
        self.last_update = time.time()

    def add_landmarks_from_dict(self, landmark_dict: dict):
        """
        Convenience: accepts dict like
          {'left_shoulder_y': 0.45, 'right_shoulder_y': 0.46}
        sent from the browser JSON payload.
        """
        lsy = landmark_dict.get('left_shoulder_y', 0.5)
        rsy = landmark_dict.get('right_shoulder_y', 0.5)
        self.add_landmark(float(lsy), float(rsy))

    # ──────────────────────────────────────────────────────────────────────────
    # SIGNAL PROCESSING
    # ──────────────────────────────────────────────────────────────────────────
    def _bandpass_filter(self, signal: np.ndarray) -> np.ndarray:
        """
        Band-pass Butterworth filter (0.1 – 0.8 Hz = 6–48 BPM).
        Keeps breathing frequencies, removes body-movement noise.
        """
        if len(signal) < 20:
            return signal
        try:
            nyq    = self.sample_rate / 2.0
            low    = 0.1  / nyq      # 6 BPM
            high   = 0.8  / nyq      # 48 BPM
            high   = min(high, 0.99)
            b, a   = butter(3, [low, high], btype='band')
            return filtfilt(b, a, signal)
        except Exception:
            return signal

    def compute_bpm(self) -> dict:
        """
        Compute current breathing BPM from buffered signal.

        Returns:
            dict with bpm, pattern, quality, status_message
        """
        if len(self.signal_buffer) < int(self.sample_rate * 8):
            # Not enough data yet
            return self._waiting_result()

        signal = np.array(self.signal_buffer)
        signal = signal - np.mean(signal)   # detrend

        filtered = self._bandpass_filter(signal)

        # Peak detection (each peak = one inhalation)
        min_peak_distance = int(self.sample_rate * 1.5)   # min 1.5 s between breaths
        peaks, _ = find_peaks(
            filtered,
            distance=min_peak_distance,
            height=np.std(filtered) * 0.3
        )

        if len(peaks) < 2:
            bpm = self.last_bpm if self.last_bpm > 0 else 0.0
        else:
            # Use actual time stamps for accuracy
            times = list(self.time_buffer)
            peak_times = [times[p] for p in peaks if p < len(times)]
            if len(peak_times) < 2:
                bpm = self.last_bpm
            else:
                intervals = np.diff(peak_times)
                mean_interval = float(np.mean(intervals))
                bpm = round(60.0 / mean_interval, 1) if mean_interval > 0 else 0.0
                # Sanity clamp
                bpm = float(np.clip(bpm, 4, 60))

        # Smooth with history
        self.bpm_history.append(bpm)
        smoothed_bpm = round(float(np.mean(self.bpm_history)), 1)
        self.last_bpm = smoothed_bpm

        # Signal quality (variance-based)
        quality = self._compute_quality(filtered)

        pattern, status_message = self._classify_pattern(smoothed_bpm)
        self.breath_events.append({'time': time.time(), 'bpm': smoothed_bpm})

        return {
            'bpm':             smoothed_bpm,
            'pattern':         pattern,
            'quality':         quality,
            'status_message':  status_message,
            'peak_count':      len(peaks),
            'buffer_size':     len(self.signal_buffer),
            'timestamp':       time.time()
        }

    # ──────────────────────────────────────────────────────────────────────────
    # CLASSIFICATION
    # ──────────────────────────────────────────────────────────────────────────
    def _classify_pattern(self, bpm: float) -> tuple:
        """Map BPM to a fitness-meaningful pattern + advice."""
        if bpm < 4:
            return ('detecting', '📡 Calibrating breathing sensor...')
        elif bpm < 10:
            return ('very_slow', '🧘 Very slow breathing — deeply relaxed state')
        elif bpm <= 20:
            return ('normal',    '✅ Normal breathing — great controlled rhythm')
        elif bpm <= 30:
            return ('elevated',  '⚡ Elevated breathing — good workout intensity')
        elif bpm <= 40:
            return ('high',      '⚠️ High breathing rate — consider slowing down')
        else:
            return ('very_high', '🛑 Very rapid breathing — take a rest break!')

    def _compute_quality(self, filtered: np.ndarray) -> str:
        """Estimate signal quality based on variance consistency."""
        if len(filtered) < 10:
            return 'low'
        snr = np.std(filtered) / (np.mean(np.abs(filtered)) + 1e-6)
        if snr > 1.5:
            return 'high'
        elif snr > 0.8:
            return 'medium'
        return 'low'

    def _waiting_result(self) -> dict:
        return {
            'bpm':             0.0,
            'pattern':         'calibrating',
            'quality':         'low',
            'status_message':  '📡 Calibrating... stay still for 8 seconds',
            'peak_count':      0,
            'buffer_size':     len(self.signal_buffer),
            'timestamp':       time.time()
        }

    # ──────────────────────────────────────────────────────────────────────────
    def get_session_breathing_log(self) -> list:
        """Return full breathing event log for ACPF dashboard."""
        return list(self.breath_events)

    def reset(self):
        self.signal_buffer.clear()
        self.time_buffer.clear()
        self.bpm_history.clear()
        self.last_bpm  = 0.0
        self.breath_events = []

    def is_ready(self) -> bool:
        return len(self.signal_buffer) >= int(self.sample_rate * 5)


if __name__ == '__main__':
    import random
    engine = BreathingEngine(sample_rate_hz=10.0)
    # Simulate 20 seconds of breathing at ~15 BPM
    print("Simulating breathing signal...")
    t = np.linspace(0, 20, 200)
    signal = 0.5 + 0.01 * np.sin(2 * np.pi * (15/60) * t) + np.random.normal(0, 0.002, 200)
    for i, y in enumerate(signal):
        engine.add_landmark(y, y + np.random.normal(0, 0.001))
        time.sleep(0.005)
    result = engine.compute_bpm()
    print(f"Estimated BPM: {result['bpm']}")
    print(f"Pattern: {result['pattern']}")
    print(f"Message: {result['status_message']}")
