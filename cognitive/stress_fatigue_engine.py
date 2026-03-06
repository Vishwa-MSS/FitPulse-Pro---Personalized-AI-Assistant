"""
stress_fatigue_engine.py
========================
Real-Time Stress & Fatigue + Motivation Score Engine for FitPulse Pro

Derives stress, fatigue, and motivation scores from the combination of:
  - Emotion signal     (from EmotionEngine)
  - Focus signal       (from GazeEngine)
  - Breathing rate     (from BreathingEngine)
  - Physical form      (from MediaPipe pose analysis)
  - Rep count & time   (from the workout session)

No additional ML model needed. Scores are computed using
evidence-based physiological formulas.
"""

import numpy as np
import time
from collections import deque


class StressFatigueEngine:
    """
    Derives 3 composite scores every time `compute()` is called:

    1. Stress Index    (0–100): higher = more stressed
    2. Fatigue Level   (0–100): higher = more fatigued
    3. Motivation Score(0–100): higher = more motivated

    All scores use exponential moving averages to prevent jarring jumps.
    """

    def __init__(self, smoothing: float = 0.25):
        """
        Args:
            smoothing: EMA alpha for temporal smoothing (0–1).
                       Lower = slower/smoother, higher = more reactive.
        """
        self.alpha = smoothing

        # EMA states
        self._stress_ema    = 50.0
        self._fatigue_ema   = 0.0
        self._motivation_ema= 50.0

        # Session tracking
        self.session_start  = time.time()
        self.history        = deque(maxlen=300)   # up to ~5 min of data
        self.rep_timestamps = []                   # when each rep was completed

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN COMPUTE
    # ──────────────────────────────────────────────────────────────────────────
    def compute(self,
                emotion_score:     float,    # 0–100 (from EmotionEngine)
                emotion_energy:    str,      # 'high' | 'medium' | 'low'
                focus_score:       float,    # 0–100 (from GazeEngine)
                bpm:               float,    # breaths/min (from BreathingEngine)
                form_score:        float,    # 0–100 (from MediaPipe analysis)
                rep_count:         int,      # current total rep count
                session_duration:  float,   # seconds elapsed this session
                is_drowsy:         bool = False
                ) -> dict:
        """
        Compute all three scores from multi-modal inputs.

        Returns:
            dict with stress, fatigue, motivation values + messages
        """

        # ── STRESS ────────────────────────────────────────────────────────────
        # High breathing + low focus + negative emotion + poor form → higher stress
        breathing_stress = self._breathing_stress(bpm)
        focus_stress     = 100 - focus_score
        emotion_stress   = self._emotion_to_stress(emotion_energy, emotion_score)
        form_stress      = max(0, 60 - form_score)   # poor form adds stress

        raw_stress = (
            breathing_stress * 0.35 +
            focus_stress     * 0.30 +
            emotion_stress   * 0.25 +
            form_stress      * 0.10
        )
        raw_stress = float(np.clip(raw_stress, 0, 100))
        self._stress_ema = self._ema(self._stress_ema, raw_stress)
        stress = round(self._stress_ema, 1)

        # ── FATIGUE ───────────────────────────────────────────────────────────
        # Duration + rep volume + drowsiness + declining form → higher fatigue
        duration_fatigue  = self._duration_fatigue(session_duration)
        rep_fatigue       = self._rep_fatigue(rep_count)
        drowsy_fatigue    = 30.0 if is_drowsy else 0.0
        form_fatigue      = max(0, 70 - form_score) * 0.5   # form degradation

        raw_fatigue = (
            duration_fatigue * 0.35 +
            rep_fatigue      * 0.25 +
            drowsy_fatigue   * 0.20 +
            form_fatigue     * 0.20
        )
        raw_fatigue = float(np.clip(raw_fatigue, 0, 100))
        self._fatigue_ema = self._ema(self._fatigue_ema, raw_fatigue)
        fatigue = round(self._fatigue_ema, 1)

        # ── MOTIVATION ────────────────────────────────────────────────────────
        # Rep pace + emotion energy + focus + low stress → higher motivation
        pace_motivation    = self._rep_pace_motivation(rep_count, session_duration)
        emotion_motivation = self._emotion_to_motivation(emotion_energy, emotion_score)
        focus_motivation   = focus_score * 0.5
        stress_drag        = stress * 0.25       # high stress drains motivation

        raw_motivation = (
            pace_motivation    * 0.30 +
            emotion_motivation * 0.35 +
            focus_motivation   * 0.20 -
            stress_drag        * 0.15
        )
        raw_motivation = float(np.clip(raw_motivation, 0, 100))
        self._motivation_ema = self._ema(self._motivation_ema, raw_motivation)
        motivation = round(self._motivation_ema, 1)

        # ── RECORD ────────────────────────────────────────────────────────────
        entry = {
            'timestamp':   time.time(),
            'stress':      stress,
            'fatigue':     fatigue,
            'motivation':  motivation,
            'bpm':         bpm,
            'focus':       focus_score,
            'form':        form_score,
            'reps':        rep_count
        }
        self.history.append(entry)

        return {
            'stress':             stress,
            'stress_message':     self._stress_message(stress),
            'stress_color':       self._score_to_color(100 - stress),
            'fatigue':            fatigue,
            'fatigue_message':    self._fatigue_message(fatigue),
            'fatigue_color':      self._score_to_color(100 - fatigue),
            'motivation':         motivation,
            'motivation_message': self._motivation_message(motivation),
            'motivation_color':   self._score_to_color(motivation),
            'timestamp':          time.time()
        }

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-SCORE HELPERS
    # ──────────────────────────────────────────────────────────────────────────
    def _ema(self, prev: float, new: float) -> float:
        return self.alpha * new + (1 - self.alpha) * prev

    def _breathing_stress(self, bpm: float) -> float:
        """Elevated BPM beyond exercise normal → stress signal."""
        if bpm <= 0:
            return 20.0
        if bpm <= 20:
            return max(0, (20 - bpm) * 2)      # slow breathing, minimal stress
        elif bpm <= 30:
            return 20.0                           # normal exercise range
        else:
            return min(100, (bpm - 30) * 4)     # above 30 BPM → rising stress

    def _emotion_to_stress(self, energy: str, score: float) -> float:
        mapping = {'high': 20.0, 'medium': 35.0, 'low': 65.0, 'unknown': 40.0}
        base = mapping.get(energy, 40.0)
        # Angry or Fear → extra stress
        adjustment = max(0, 50 - score) * 0.4
        return min(100, base + adjustment)

    def _emotion_to_motivation(self, energy: str, score: float) -> float:
        mapping = {'high': 80.0, 'medium': 55.0, 'low': 25.0, 'unknown': 50.0}
        return min(100, mapping.get(energy, 50.0) * (score / 100))

    def _duration_fatigue(self, seconds: float) -> float:
        """Fatigue rises with session duration (logarithmic)."""
        if seconds <= 0:
            return 0.0
        minutes = seconds / 60.0
        # After 10 min starts building; 60 min → ~85% fatigue
        return float(np.clip(18 * np.log1p(max(0, minutes - 5)), 0, 85))

    def _rep_fatigue(self, reps: int) -> float:
        """More reps → more fatigue (diminishing return curve)."""
        return float(np.clip(12 * np.log1p(reps), 0, 70))

    def _rep_pace_motivation(self, reps: int, seconds: float) -> float:
        """Consistent rep pace = high motivation."""
        if seconds < 10 or reps == 0:
            return 50.0
        reps_per_min = reps / (seconds / 60.0)
        if 5 <= reps_per_min <= 25:
            return 75.0
        elif reps_per_min < 5:
            return 40.0
        return 55.0

    # ──────────────────────────────────────────────────────────────────────────
    # MESSAGES
    # ──────────────────────────────────────────────────────────────────────────
    def _stress_message(self, stress: float) -> str:
        if stress < 25:
            return '😌 Very calm — optimal state for performance'
        elif stress < 50:
            return '✅ Manageable stress — stay focused'
        elif stress < 70:
            return '⚠️ Elevated stress — control your breathing'
        return '🛑 High stress — take a short break now'

    def _fatigue_message(self, fatigue: float) -> str:
        if fatigue < 25:
            return '💪 Fresh and strong — push your limits!'
        elif fatigue < 50:
            return '✅ Mild fatigue — maintain your form'
        elif fatigue < 70:
            return '⚠️ Moderate fatigue — consider rest sets'
        return '🛑 High fatigue — stop and rest to avoid injury'

    def _motivation_message(self, motivation: float) -> str:
        if motivation >= 75:
            return '🔥 You are on fire! Keep crushing it!'
        elif motivation >= 50:
            return '💪 Good drive — stay consistent!'
        elif motivation >= 30:
            return '😐 Motivation dipping — remember your goal!'
        return '😓 Low motivation — rest or switch activity'

    def _score_to_color(self, score: float) -> str:
        """Green=high, Yellow=medium, Red=low."""
        if score >= 70:
            return '#10b981'
        elif score >= 40:
            return '#f59e0b'
        return '#ef4444'

    # ──────────────────────────────────────────────────────────────────────────
    def get_session_history(self) -> list:
        return list(self.history)

    def reset(self):
        self._stress_ema     = 50.0
        self._fatigue_ema    = 0.0
        self._motivation_ema = 50.0
        self.session_start   = time.time()
        self.history.clear()
        self.rep_timestamps  = []


if __name__ == '__main__':
    engine = StressFatigueEngine()
    result = engine.compute(
        emotion_score=70, emotion_energy='high',
        focus_score=65, bpm=18, form_score=80,
        rep_count=10, session_duration=120
    )
    for k, v in result.items():
        print(f"  {k}: {v}")
