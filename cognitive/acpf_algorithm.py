
import numpy as np
import time
import json
from typing import Dict, List, Tuple, Optional
from enum import Enum
from collections import deque
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

class ExerciseType(Enum):
    STRENGTH    = "strength"
    CARDIO      = "cardio"
    BALANCE     = "balance"
    FLEXIBILITY = "flexibility"


class RiskLevel(Enum):
    SAFE    = "SAFE"
    CAUTION = "CAUTION"
    STOP    = "STOP"


class PhysicalState:
    def __init__(self, form_score: float, range_of_motion: float,
                 movement_smoothness: float, rep_count: int = 0,
                 angle: float = 0.0):
        self.form_score         = float(np.clip(form_score, 0, 100))
        self.range_of_motion    = float(np.clip(range_of_motion, 0, 100))
        self.movement_smoothness= float(np.clip(movement_smoothness, 0, 100))
        self.rep_count          = int(rep_count)
        self.angle              = float(angle)

    def to_dict(self):
        return {
            'form_score':          self.form_score,
            'range_of_motion':     self.range_of_motion,
            'movement_smoothness': self.movement_smoothness,
            'rep_count':           self.rep_count,
            'angle':               self.angle
        }


class CognitiveState:
    def __init__(self, focus_score: float, stress_index: float,
                 fatigue_level: float, breathing_rate: float,
                 emotion: str = 'Neutral', emotion_score: float = 65.0,
                 motivation: float = 50.0):
        self.focus_score    = float(np.clip(focus_score, 0, 100))
        self.stress_index   = float(np.clip(stress_index, 0, 100))
        self.fatigue_level  = float(np.clip(fatigue_level, 0, 100))
        self.breathing_rate = float(np.clip(breathing_rate, 4, 60))
        self.emotion        = emotion
        self.emotion_score  = float(np.clip(emotion_score, 0, 100))
        self.motivation     = float(np.clip(motivation, 0, 100))

    def to_dict(self):
        return {
            'focus_score':    self.focus_score,
            'stress_index':   self.stress_index,
            'fatigue_level':  self.fatigue_level,
            'breathing_rate': self.breathing_rate,
            'emotion':        self.emotion,
            'emotion_score':  self.emotion_score,
            'motivation':     self.motivation
        }


class FusedWellnessState:
    def __init__(self, overall_wellness: float, physical_component: float,
                 cognitive_component: float, attention_weights: Dict[str, float],
                 risk_level: RiskLevel, recommended_action: str,
                 adjustments_made: List[str], acpf_score: float):
        self.overall_wellness    = overall_wellness
        self.physical_component  = physical_component
        self.cognitive_component = cognitive_component
        self.attention_weights   = attention_weights
        self.risk_level          = risk_level
        self.recommended_action  = recommended_action
        self.adjustments_made    = adjustments_made
        self.acpf_score          = acpf_score
        self.timestamp           = time.time()

    def to_dict(self):
        return {
            'overall_wellness':    round(self.overall_wellness, 2),
            'physical_component':  round(self.physical_component, 2),
            'cognitive_component': round(self.cognitive_component, 2),
            'acpf_score':          round(self.acpf_score, 2),
            'attention_weights':   {k: round(v, 3) for k, v in self.attention_weights.items()},
            'risk_level':          self.risk_level.value,
            'recommended_action':  self.recommended_action,
            'adjustments_made':    self.adjustments_made,
            'timestamp':           self.timestamp
        }


# ══════════════════════════════════════════════════════════════════════════════
# ACPF ALGORITHM — CORE
# ══════════════════════════════════════════════════════════════════════════════

class ACPFAlgorithm:
    

    # ── Base weight profiles (sum = 1.0) ──────────────────────────────────────
    BASE_WEIGHTS = {
        ExerciseType.STRENGTH: {
            'form_score': 0.25, 'range_of_motion': 0.20,
            'movement_smoothness': 0.15, 'focus_score': 0.15,
            'fatigue_level': 0.15, 'stress_index': 0.05, 'breathing_rate': 0.05
        },
        ExerciseType.CARDIO: {
            'form_score': 0.15, 'range_of_motion': 0.10,
            'movement_smoothness': 0.10, 'focus_score': 0.10,
            'fatigue_level': 0.20, 'stress_index': 0.10, 'breathing_rate': 0.25
        },
        ExerciseType.BALANCE: {
            'form_score': 0.20, 'range_of_motion': 0.10,
            'movement_smoothness': 0.15, 'focus_score': 0.30,
            'fatigue_level': 0.10, 'stress_index': 0.10, 'breathing_rate': 0.05
        },
        ExerciseType.FLEXIBILITY: {
            'form_score': 0.20, 'range_of_motion': 0.25,
            'movement_smoothness': 0.15, 'focus_score': 0.15,
            'fatigue_level': 0.10, 'stress_index': 0.10, 'breathing_rate': 0.05
        }
    }

    THRESHOLDS = {
        'high_fatigue':    70,
        'critical_fatigue':85,
        'high_stress':     65,
        'critical_stress': 80,
        'poor_form':       55,
        'low_focus':       45
    }

    BREATHING_RANGES = {
        ExerciseType.STRENGTH:    {'optimal': 15, 'min': 10, 'max': 22},
        ExerciseType.CARDIO:      {'optimal': 25, 'min': 18, 'max': 40},
        ExerciseType.BALANCE:     {'optimal': 14, 'min': 10, 'max': 20},
        ExerciseType.FLEXIBILITY: {'optimal': 13, 'min': 8,  'max': 18}
    }

    def __init__(self, exercise_type: ExerciseType = ExerciseType.STRENGTH,
                 smoothing_factor: float = 0.3,
                 athlete_name: str = 'Athlete',
                 exercise_name: str = 'Exercise'):
        self.exercise_type   = exercise_type
        self.smoothing_factor= smoothing_factor
        self.athlete_name    = athlete_name
        self.exercise_name   = exercise_name

        self.base_weights  = self.BASE_WEIGHTS[exercise_type].copy()
        self.prev_wellness = None

        # Session data for dashboard
        self.session_id    = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_start = time.time()
        self.session_log   : List[dict] = []     # full per-frame log
        self.rep_log       : List[dict] = []     # per-rep snapshots
        self.event_log     : List[dict] = []     # notable events
        self._prev_rep_count = 0

        # Stats
        self.total_frames     = 0
        self.adjustment_count = 0
        self.history_buffer   = deque(maxlen=50)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1+2: DYNAMIC WEIGHT ADJUSTMENT (Key Innovation)
    # ──────────────────────────────────────────────────────────────────────────
    def _compute_dynamic_weights(self, physical: PhysicalState,
                                  cognitive: CognitiveState
                                  ) -> Tuple[Dict[str, float], List[str]]:
        """
        Dynamically adjusts attention weights based on real-time threshold crossings.

        This is the core of the ACPF innovation — weights are NOT static.
        They react to the athlete's live state, prioritising the most
        safety-critical dimension at any given moment.
        """
        weights     = self.base_weights.copy()
        adjustments = []

        # ── Rule 1: High Fatigue → Prioritise safety monitoring ───────────────
        if cognitive.fatigue_level > self.THRESHOLDS['high_fatigue']:
            severity = (cognitive.fatigue_level - self.THRESHOLDS['high_fatigue']) / 30
            boost    = 0.20 * severity
            weights['fatigue_level']        += boost
            weights['form_score']           -= boost * 0.5
            weights['range_of_motion']      -= boost * 0.5
            adjustments.append(f'HighFatigue({cognitive.fatigue_level:.0f}%): fatigue_wt+{boost:.3f}')

        # ── Rule 2: High Stress → Elevate mental state monitoring ─────────────
        if cognitive.stress_index > self.THRESHOLDS['high_stress']:
            severity = (cognitive.stress_index - self.THRESHOLDS['high_stress']) / 35
            boost    = 0.15 * severity
            weights['stress_index']         += boost
            weights['focus_score']          += boost * 0.5
            weights['movement_smoothness']  -= boost * 0.5
            adjustments.append(f'HighStress({cognitive.stress_index:.0f}%): stress_wt+{boost:.3f}')

        # ── Rule 3: Poor Form → Injury prevention override ────────────────────
        if physical.form_score < self.THRESHOLDS['poor_form']:
            severity = (self.THRESHOLDS['poor_form'] - physical.form_score) / 55
            boost    = 0.20 * severity
            weights['form_score']           += boost
            weights['focus_score']          += boost * 0.5
            weights['breathing_rate']       -= boost * 0.5
            adjustments.append(f'PoorForm({physical.form_score:.0f}): form_wt+{boost:.3f}')

        # ── Rule 4: Low Focus → Attention prioritisation ──────────────────────
        if cognitive.focus_score < self.THRESHOLDS['low_focus']:
            severity = (self.THRESHOLDS['low_focus'] - cognitive.focus_score) / 45
            boost    = 0.15 * severity
            weights['focus_score']          += boost
            weights['form_score']           += boost * 0.3
            adjustments.append(f'LowFocus({cognitive.focus_score:.0f}%): focus_wt+{boost:.3f}')

        # ── Rule 5: Abnormal Breathing ────────────────────────────────────────
        br   = self.BREATHING_RANGES[self.exercise_type]
        if not (br['min'] <= cognitive.breathing_rate <= br['max']):
            weights['breathing_rate']       += 0.10
            weights['fatigue_level']        += 0.05
            adjustments.append(f'AbnormalBreathing({cognitive.breathing_rate:.0f}BPM): br_wt+0.10')

        # ── Normalise → sum = 1.0 ─────────────────────────────────────────────
        total   = sum(weights.values())
        weights = {k: max(0, v / total) for k, v in weights.items()}

        if adjustments:
            self.adjustment_count += 1

        return weights, adjustments

    # ──────────────────────────────────────────────────────────────────────────
    # STEPS 3–5: COMPONENT SCORES
    # ──────────────────────────────────────────────────────────────────────────
    def _compute_component_scores(self, physical: PhysicalState,
                                   cognitive: CognitiveState,
                                   weights: Dict[str, float]) -> Tuple[float, float]:
        br_ranges = self.BREATHING_RANGES[self.exercise_type]
        optimal   = br_ranges['optimal']
        max_dev   = (br_ranges['max'] - br_ranges['min']) / 2
        br_score  = float(np.clip(100 - abs(cognitive.breathing_rate - optimal) / max_dev * 100, 0, 100))

        physical_score = (
            physical.form_score          * weights['form_score'] +
            physical.range_of_motion     * weights['range_of_motion'] +
            physical.movement_smoothness * weights['movement_smoothness']
        )

        cognitive_score = (
            cognitive.focus_score                  * weights['focus_score'] +
            (100 - cognitive.fatigue_level)        * weights['fatigue_level'] +
            (100 - cognitive.stress_index)         * weights['stress_index'] +
            br_score                               * weights['breathing_rate']
        )

        return float(physical_score), float(cognitive_score)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 6: TEMPORAL SMOOTHING (EMA)
    # ──────────────────────────────────────────────────────────────────────────
    def _smooth(self, raw: float) -> float:
        if self.prev_wellness is None:
            self.prev_wellness = raw
            return raw
        smoothed = self.smoothing_factor * raw + (1 - self.smoothing_factor) * self.prev_wellness
        self.prev_wellness = smoothed
        return smoothed

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 7: RISK ASSESSMENT
    # ──────────────────────────────────────────────────────────────────────────
    def _assess_risk(self, wellness: float, physical: PhysicalState,
                     cognitive: CognitiveState) -> Tuple[RiskLevel, str]:

        if cognitive.fatigue_level > self.THRESHOLDS['critical_fatigue']:
            return (RiskLevel.STOP,
                    f'⛔ CRITICAL FATIGUE ({cognitive.fatigue_level:.0f}%) — Stop immediately and rest!')

        if cognitive.stress_index > self.THRESHOLDS['critical_stress']:
            return (RiskLevel.STOP,
                    f'⛔ CRITICAL STRESS ({cognitive.stress_index:.0f}%) — Breathe deeply and rest!')

        if wellness >= 70:
            return (RiskLevel.SAFE,
                    '✅ Excellent wellness! Maintain this intensity.')
        elif wellness >= 50:
            return (RiskLevel.CAUTION,
                    '⚠️ Moderate wellness — watch your form and breathing.')
        else:
            return (RiskLevel.STOP,
                    '⛔ Low wellness — take a rest before continuing.')

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN FUSE (call every frame)
    # ──────────────────────────────────────────────────────────────────────────
    def fuse(self, physical: PhysicalState,
             cognitive: CognitiveState) -> FusedWellnessState:

        self.total_frames += 1

        weights, adjustments = self._compute_dynamic_weights(physical, cognitive)
        phys_score, cog_score = self._compute_component_scores(physical, cognitive, weights)

        w_phys   = weights['form_score'] + weights['range_of_motion'] + weights['movement_smoothness']
        w_cog    = 1.0 - w_phys
        raw_well = phys_score * w_phys + cog_score * w_cog
        wellness = self._smooth(raw_well)

        # ACPF composite score (proprietary weighting)
        acpf_score = float(np.clip(
            wellness * 0.5 + cognitive.motivation * 0.3 + physical.form_score * 0.2,
            0, 100
        ))

        risk_level, action = self._assess_risk(wellness, physical, cognitive)

        # ── Log this frame ────────────────────────────────────────────────────
        entry = {
            'ts':               time.time(),
            'elapsed':          round(time.time() - self.session_start, 1),
            'wellness':         round(wellness, 2),
            'acpf_score':       round(acpf_score, 2),
            'physical':         round(phys_score, 2),
            'cognitive':        round(cog_score, 2),
            'form':             physical.form_score,
            'range_of_motion':  physical.range_of_motion,
            'smoothness':       physical.movement_smoothness,
            'reps':             physical.rep_count,
            'angle':            physical.angle,
            'focus':            cognitive.focus_score,
            'fatigue':          cognitive.fatigue_level,
            'stress':           cognitive.stress_index,
            'breathing':        cognitive.breathing_rate,
            'emotion':          cognitive.emotion,
            'motivation':       cognitive.motivation,
            'risk':             risk_level.value,
            'weights':          {k: round(v, 3) for k, v in weights.items()},
            'adjustments':      adjustments
        }
        self.session_log.append(entry)
        self.history_buffer.append(entry)

        # ── Detect new rep completed ──────────────────────────────────────────
        if physical.rep_count > self._prev_rep_count:
            self.rep_log.append({
                'rep_num':    physical.rep_count,
                'ts':         entry['ts'],
                'elapsed':    entry['elapsed'],
                'form':       physical.form_score,
                'angle':      physical.angle,
                'wellness':   round(wellness, 2),
                'fatigue':    cognitive.fatigue_level,
                'focus':      cognitive.focus_score,
                'emotion':    cognitive.emotion
            })
            self._prev_rep_count = physical.rep_count

        # ── Log notable events ────────────────────────────────────────────────
        if risk_level == RiskLevel.STOP and adjustments:
            self.event_log.append({
                'ts':      entry['ts'],
                'elapsed': entry['elapsed'],
                'event':   'RISK_STOP',
                'detail':  action
            })

        return FusedWellnessState(
            overall_wellness    = wellness,
            physical_component  = phys_score,
            cognitive_component = cog_score,
            attention_weights   = weights,
            risk_level          = risk_level,
            recommended_action  = action,
            adjustments_made    = adjustments,
            acpf_score          = acpf_score
        )

    # ──────────────────────────────────────────────────────────────────────────
    # TREND ANALYSIS
    # ──────────────────────────────────────────────────────────────────────────
    def get_wellness_trend(self) -> dict:
        if len(self.history_buffer) < 5:
            return {'trend': 0.0, 'direction': 'stable', 'confidence': 'low'}
        vals  = [e['wellness'] for e in list(self.history_buffer)[-15:]]
        x     = np.arange(len(vals))
        slope = float(np.polyfit(x, vals, 1)[0])
        direction = 'improving' if slope > 1 else ('declining' if slope < -1 else 'stable')
        return {'trend': round(slope, 3), 'direction': direction,
                'confidence': 'high' if len(vals) >= 10 else 'medium'}

    # ──────────────────────────────────────────────────────────────────────────
    # SESSION SUMMARY (for API)
    # ──────────────────────────────────────────────────────────────────────────
    def get_session_summary(self) -> dict:
        if not self.session_log:
            return {}

        log   = self.session_log
        wells = [e['wellness']  for e in log]
        forms = [e['form']      for e in log]
        fats  = [e['fatigue']   for e in log]
        focs  = [e['focus']     for e in log]
        strs  = [e['stress']    for e in log]
        brths = [e['breathing'] for e in log]
        mots  = [e['motivation']for e in log]
        acpfs = [e['acpf_score']for e in log]

        duration_s = time.time() - self.session_start

        return {
            'session_id':          self.session_id,
            'athlete_name':        self.athlete_name,
            'exercise':            self.exercise_name,
            'exercise_type':       self.exercise_type.value,
            'duration_seconds':    round(duration_s, 1),
            'duration_formatted':  f"{int(duration_s//60)}m {int(duration_s%60)}s",
            'total_frames':        self.total_frames,
            'total_reps':          self._prev_rep_count,
            'date':                datetime.now().strftime('%Y-%m-%d %H:%M'),

            # Score averages
            'avg_wellness':        round(float(np.mean(wells)), 1),
            'avg_form':            round(float(np.mean(forms)), 1),
            'avg_fatigue':         round(float(np.mean(fats)),  1),
            'avg_focus':           round(float(np.mean(focs)),  1),
            'avg_stress':          round(float(np.mean(strs)),  1),
            'avg_breathing':       round(float(np.mean(brths)), 1),
            'avg_motivation':      round(float(np.mean(mots)),  1),
            'avg_acpf':            round(float(np.mean(acpfs)), 1),

            # Peaks / troughs
            'peak_wellness':       round(float(np.max(wells)), 1),
            'lowest_wellness':     round(float(np.min(wells)), 1),
            'peak_form':           round(float(np.max(forms)), 1),
            'peak_motivation':     round(float(np.max(mots)),  1),

            # Adaptive weight adjustment count
            'adjustment_count':    self.adjustment_count,

            # Rep-level detail
            'rep_log':             self.rep_log,
            'event_log':           self.event_log,

            # Time series (sampled for dashboard)
            'timeline':            self._sample_timeline(100)
        }

    def _sample_timeline(self, n: int = 100) -> list:
        """Downsample session log to n points for dashboard charts."""
        log = self.session_log
        if len(log) <= n:
            return log
        step  = len(log) / n
        return [log[int(i * step)] for i in range(n)]

    # ──────────────────────────────────────────────────────────────────────────
    # DASHBOARD GENERATOR
    # ──────────────────────────────────────────────────────────────────────────
    def generate_dashboard(self) -> str:
        """
        Generate a fully self-contained interactive HTML dashboard
        with Chart.js visualisations for the completed workout session.

        Returns:
            HTML string ready to be saved as .html file or served directly.
        """
        summary  = self.get_session_summary()
        timeline = summary.get('timeline', [])
        rep_log  = summary.get('rep_log', [])
        events   = summary.get('event_log', [])

        # JSON-serialise time series for charts
        labels       = [round(e['elapsed'], 1) for e in timeline]
        wellness_ts  = [round(e['wellness'],  1) for e in timeline]
        form_ts      = [round(e['form'],      1) for e in timeline]
        focus_ts     = [round(e['focus'],     1) for e in timeline]
        fatigue_ts   = [round(e['fatigue'],   1) for e in timeline]
        stress_ts    = [round(e['stress'],    1) for e in timeline]
        motivation_ts= [round(e['motivation'],1) for e in timeline]
        breathing_ts = [round(e['breathing'], 1) for e in timeline]
        acpf_ts      = [round(e['acpf_score'],1) for e in timeline]

        rep_labels   = [f"Rep {r['rep_num']}" for r in rep_log]
        rep_form     = [round(r['form'],    1) for r in rep_log]
        rep_fatigue  = [round(r['fatigue'], 1) for r in rep_log]
        rep_focus    = [round(r['focus'],   1) for r in rep_log]
        rep_wellness = [round(r['wellness'],1) for r in rep_log]

        def grade(score):
            if score >= 80: return ('A', '🏆', '#10b981')
            if score >= 65: return ('B', '✅', '#22d3ee')
            if score >= 50: return ('C', '⚠️', '#f59e0b')
            return ('D', '⛔', '#ef4444')

        well_grade = grade(summary.get('avg_wellness', 0))
        form_grade = grade(summary.get('avg_form', 0))
        acpf_grade = grade(summary.get('avg_acpf', 0))

        events_html = ''.join(
            f'<tr><td>{round(ev["elapsed"],1)}s</td>'
            f'<td><span class="badge badge-stop">{ev["event"]}</span></td>'
            f'<td>{ev["detail"]}</td></tr>'
            for ev in events
        ) or '<tr><td colspan="3" style="text-align:center;color:#10b981;">✅ No critical events — great session!</td></tr>'

        rep_rows_html = ''.join(
            f'<tr><td>Rep {r["rep_num"]}</td>'
            f'<td>{round(r["elapsed"],1)}s</td>'
            f'<td>{round(r["form"],1)}%</td>'
            f'<td>{round(r.get("angle",0),1)}°</td>'
            f'<td>{r["emotion"]}</td>'
            f'<td>{round(r["fatigue"],1)}%</td>'
            f'<td>{round(r["focus"],1)}%</td></tr>'
            for r in rep_log
        ) or '<tr><td colspan="7" style="text-align:center;color:#6b7280;">No reps recorded</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>FitPulse Pro — ACPF Athlete Dashboard | {summary.get('athlete_name','Athlete')} | {summary.get('date','')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#1e40af,#7c3aed);padding:32px 40px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}}
  .header h1{{font-size:28px;font-weight:800;color:#fff}}
  .header h1 span{{color:#fbbf24}}
  .header-meta{{color:rgba(255,255,255,0.8);font-size:14px;line-height:1.8}}
  .header-badge{{background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);border-radius:8px;padding:8px 16px;color:#fff;font-size:13px;backdrop-filter:blur(4px)}}
  .container{{max-width:1400px;margin:0 auto;padding:32px 24px}}
  .section-title{{font-size:20px;font-weight:700;color:#f1f5f9;margin:32px 0 16px;display:flex;align-items:center;gap:10px}}
  .section-title::before{{content:'';display:block;width:4px;height:24px;background:linear-gradient(#3b82f6,#8b5cf6);border-radius:2px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:32px}}
  .card{{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:20px;text-align:center;transition:transform .2s}}
  .card:hover{{transform:translateY(-2px)}}
  .card-icon{{font-size:28px;margin-bottom:8px}}
  .card-label{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:6px}}
  .card-value{{font-size:26px;font-weight:800;margin-bottom:4px}}
  .card-grade{{font-size:13px;color:#94a3b8}}
  .chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:32px}}
  .chart-grid.full{{grid-template-columns:1fr}}
  .chart-card{{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:24px}}
  .chart-card h3{{font-size:15px;font-weight:600;color:#94a3b8;margin-bottom:16px;text-transform:uppercase;letter-spacing:.5px}}
  .chart-wrapper{{position:relative;height:280px}}
  table{{width:100%;border-collapse:collapse;font-size:14px}}
  th{{background:#0f172a;color:#64748b;text-transform:uppercase;font-size:11px;letter-spacing:.5px;padding:12px 16px;text-align:left}}
  td{{padding:12px 16px;border-bottom:1px solid #1e293b;color:#cbd5e1}}
  tr:hover td{{background:#1e293b}}
  .table-card{{background:#1e293b;border:1px solid #334155;border-radius:16px;overflow:hidden;margin-bottom:32px}}
  .badge{{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}}
  .badge-stop{{background:#7f1d1d;color:#fca5a5}}
  .acpf-banner{{background:linear-gradient(135deg,#1e3a8a22,#6d28d922);border:1px solid #3b82f633;border-radius:16px;padding:24px;margin-bottom:32px;text-align:center}}
  .acpf-score-big{{font-size:72px;font-weight:900;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1}}
  .acpf-label{{font-size:14px;color:#64748b;margin-top:8px;text-transform:uppercase;letter-spacing:2px}}
  .acpf-desc{{font-size:15px;color:#94a3b8;margin-top:12px;max-width:600px;margin-inline:auto}}
  .dl-btn{{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff;border:none;border-radius:10px;padding:12px 28px;font-size:15px;font-weight:700;cursor:pointer;text-decoration:none;transition:opacity .2s}}
  .dl-btn:hover{{opacity:.85}}
  .footer{{text-align:center;padding:32px;color:#475569;font-size:13px;border-top:1px solid #1e293b;margin-top:32px}}
  @media(max-width:768px){{.chart-grid{{grid-template-columns:1fr}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>💪 FitPulse Pro — <span>ACPF Dashboard</span></h1>
    <div class="header-meta">
      Athlete: <strong>{summary.get('athlete_name','Athlete')}</strong> &nbsp;|&nbsp;
      Exercise: <strong>{summary.get('exercise','N/A')}</strong> &nbsp;|&nbsp;
      Date: <strong>{summary.get('date','N/A')}</strong>
    </div>
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
    <div class="header-badge">⏱ {summary.get('duration_formatted','N/A')}</div>
    <div class="header-badge">🔁 {summary.get('total_reps',0)} Reps</div>
    <div class="header-badge">📊 {summary.get('exercise_type','strength').title()}</div>
    <button class="dl-btn" onclick="window.print()">🖨️ Print / Save PDF</button>
  </div>
</div>

<div class="container">

  <!-- ACPF COMPOSITE SCORE BANNER -->
  <div class="section-title">ACPF Composite Score</div>
  <div class="acpf-banner">
    <div class="acpf-score-big">{summary.get('avg_acpf',0)}</div>
    <div class="acpf-label">/ 100 &nbsp;•&nbsp; Adaptive Cognitive-Physical Fusion Score</div>
    <div class="acpf-desc">
      The ACPF Score is a dynamic fusion of physical form quality, cognitive state,
      and adaptive attention weights that change in real time based on your body's signals.
      Grade: <strong style="color:{acpf_grade[2]}">{acpf_grade[0]} {acpf_grade[1]}</strong>
    </div>
  </div>

  <!-- KEY METRICS CARDS -->
  <div class="section-title">Session Metrics Overview</div>
  <div class="cards">
    <div class="card">
      <div class="card-icon">🧘</div>
      <div class="card-label">Avg Wellness</div>
      <div class="card-value" style="color:{well_grade[2]}">{summary.get('avg_wellness',0)}%</div>
      <div class="card-grade">Grade {well_grade[0]} {well_grade[1]}</div>
    </div>
    <div class="card">
      <div class="card-icon">🎯</div>
      <div class="card-label">Avg Form</div>
      <div class="card-value" style="color:{form_grade[2]}">{summary.get('avg_form',0)}%</div>
      <div class="card-grade">Peak {summary.get('peak_form',0)}%</div>
    </div>
    <div class="card">
      <div class="card-icon">👁️</div>
      <div class="card-label">Avg Focus</div>
      <div class="card-value" style="color:#22d3ee">{summary.get('avg_focus',0)}%</div>
      <div class="card-grade">Gaze Score</div>
    </div>
    <div class="card">
      <div class="card-icon">😴</div>
      <div class="card-label">Avg Fatigue</div>
      <div class="card-value" style="color:#f59e0b">{summary.get('avg_fatigue',0)}%</div>
      <div class="card-grade">Lower is better</div>
    </div>
    <div class="card">
      <div class="card-icon">😤</div>
      <div class="card-label">Avg Stress</div>
      <div class="card-value" style="color:#f97316">{summary.get('avg_stress',0)}%</div>
      <div class="card-grade">Lower is better</div>
    </div>
    <div class="card">
      <div class="card-icon">🫁</div>
      <div class="card-label">Avg Breathing</div>
      <div class="card-value" style="color:#a78bfa">{summary.get('avg_breathing',0)}</div>
      <div class="card-grade">BPM</div>
    </div>
    <div class="card">
      <div class="card-icon">🔥</div>
      <div class="card-label">Avg Motivation</div>
      <div class="card-value" style="color:#fb923c">{summary.get('avg_motivation',0)}%</div>
      <div class="card-grade">Peak {summary.get('peak_motivation',0)}%</div>
    </div>
    <div class="card">
      <div class="card-icon">⚡</div>
      <div class="card-label">Adaptations</div>
      <div class="card-value" style="color:#e879f9">{summary.get('adjustment_count',0)}</div>
      <div class="card-grade">Weight shifts</div>
    </div>
  </div>

  <!-- CHARTS: TIME SERIES -->
  <div class="section-title">Real-Time Performance Timeline</div>
  <div class="chart-grid">
    <div class="chart-card">
      <h3>🧘 Wellness + ACPF Score Over Time</h3>
      <div class="chart-wrapper">
        <canvas id="wellnessChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h3>🎯 Form + Focus Over Time</h3>
      <div class="chart-wrapper">
        <canvas id="formFocusChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h3>😴 Fatigue + Stress Over Time</h3>
      <div class="chart-wrapper">
        <canvas id="fatigueStressChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h3>🫁 Breathing Rate + Motivation Over Time</h3>
      <div class="chart-wrapper">
        <canvas id="breathingChart"></canvas>
      </div>
    </div>
  </div>

  <!-- RADAR CHART -->
  <div class="chart-grid full">
    <div class="chart-card" style="display:flex;gap:24px;flex-wrap:wrap">
      <div style="flex:1;min-width:280px">
        <h3>📊 Athlete Performance Radar</h3>
        <div class="chart-wrapper">
          <canvas id="radarChart"></canvas>
        </div>
      </div>
      <div style="flex:1;min-width:280px">
        <h3>🔁 Per-Rep Quality Analysis</h3>
        <div class="chart-wrapper">
          <canvas id="repChart"></canvas>
        </div>
      </div>
    </div>
  </div>

  <!-- REP LOG TABLE -->
  <div class="section-title">Rep-by-Rep Breakdown</div>
  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th>Rep</th><th>Time</th><th>Form %</th>
          <th>Angle</th><th>Emotion</th><th>Fatigue %</th><th>Focus %</th>
        </tr>
      </thead>
      <tbody>
        {rep_rows_html}
      </tbody>
    </table>
  </div>

  <!-- EVENTS TABLE -->
  <div class="section-title">Critical Events Log</div>
  <div class="table-card">
    <table>
      <thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead>
      <tbody>{events_html}</tbody>
    </table>
  </div>

  <!-- ACPF INNOVATION EXPLANATION -->
  <div class="section-title">About the ACPF Algorithm</div>
  <div class="acpf-banner" style="text-align:left;padding:28px 32px">
    <h3 style="color:#93c5fd;margin-bottom:12px;font-size:18px">⚙️ Adaptive Cognitive-Physical Fusion (ACPF)</h3>
    <p style="color:#cbd5e1;line-height:1.8;font-size:14px">
      ACPF is a real-time multi-modal fusion algorithm designed for intelligent athletic performance monitoring.
      Unlike static weighted systems, ACPF <strong style="color:#a78bfa">dynamically adjusts attention weights</strong>
      at every frame based on threshold-crossing rules across 7 biometric dimensions
      (form, range of motion, smoothness, focus, fatigue, stress, breathing).
      <br/><br/>
      During this session, the algorithm made <strong style="color:#fbbf24">{summary.get('adjustment_count',0)} adaptive weight adjustments</strong>,
      redistributing attention toward the most safety-critical signals in real time.
      This enables personalised, intelligent coaching that responds to each athlete's unique state.
    </p>
  </div>

</div>

<div class="footer">
  Generated by FitPulse Pro — ACPF Cognitive Fitness System &nbsp;|&nbsp;
  Session ID: {summary.get('session_id','N/A')} &nbsp;|&nbsp;
  {summary.get('date','N/A')}
</div>

<script>
const labels        = {json.dumps(labels)};
const wellnessTS    = {json.dumps(wellness_ts)};
const acpfTS        = {json.dumps(acpf_ts)};
const formTS        = {json.dumps(form_ts)};
const focusTS       = {json.dumps(focus_ts)};
const fatigueTS     = {json.dumps(fatigue_ts)};
const stressTS      = {json.dumps(stress_ts)};
const motivationTS  = {json.dumps(motivation_ts)};
const breathingTS   = {json.dumps(breathing_ts)};
const repLabels     = {json.dumps(rep_labels)};
const repForm       = {json.dumps(rep_form)};
const repFatigue    = {json.dumps(rep_fatigue)};
const repFocus      = {json.dumps(rep_focus)};
const repWellness   = {json.dumps(rep_wellness)};

const chartDefaults = {{
  responsive:true, maintainAspectRatio:false,
  plugins:{{legend:{{labels:{{color:'#94a3b8',font:{{size:12}}}}}}}},
  scales:{{
    x:{{ticks:{{color:'#64748b',maxTicksLimit:10}},grid:{{color:'#1e293b'}}}},
    y:{{ticks:{{color:'#64748b'}},grid:{{color:'#1e293b'}},min:0,max:100}}
  }}
}};

// Wellness chart
new Chart(document.getElementById('wellnessChart'),{{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{label:'Wellness',data:wellnessTS,borderColor:'#3b82f6',backgroundColor:'#3b82f615',tension:.4,fill:true,pointRadius:0}},
      {{label:'ACPF Score',data:acpfTS,borderColor:'#8b5cf6',backgroundColor:'#8b5cf615',tension:.4,fill:true,pointRadius:0}}
    ]
  }},
  options:{{...chartDefaults,scales:{{...chartDefaults.scales,x:{{...chartDefaults.scales.x,title:{{display:true,text:'Elapsed (s)',color:'#64748b'}}}}}}}}
}});

// Form + Focus
new Chart(document.getElementById('formFocusChart'),{{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{label:'Form %',data:formTS,borderColor:'#10b981',tension:.4,pointRadius:0}},
      {{label:'Focus %',data:focusTS,borderColor:'#22d3ee',tension:.4,pointRadius:0}}
    ]
  }},
  options:chartDefaults
}});

// Fatigue + Stress
new Chart(document.getElementById('fatigueStressChart'),{{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{label:'Fatigue %',data:fatigueTS,borderColor:'#f59e0b',tension:.4,pointRadius:0}},
      {{label:'Stress %',data:stressTS,borderColor:'#ef4444',tension:.4,pointRadius:0}}
    ]
  }},
  options:chartDefaults
}});

// Breathing + Motivation
new Chart(document.getElementById('breathingChart'),{{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{label:'Breathing (BPM)',data:breathingTS,borderColor:'#a78bfa',tension:.4,pointRadius:0,
        yAxisID:'bpm'}},
      {{label:'Motivation %',data:motivationTS,borderColor:'#fb923c',tension:.4,pointRadius:0}}
    ]
  }},
  options:{{
    ...chartDefaults,
    scales:{{
      x:chartDefaults.scales.x,
      y:{{...chartDefaults.scales.y,position:'left'}},
      bpm:{{position:'right',min:0,max:50,ticks:{{color:'#a78bfa'}},grid:{{display:false}}}}
    }}
  }}
}});

// Radar
new Chart(document.getElementById('radarChart'),{{
  type:'radar',
  data:{{
    labels:['Wellness','Form','Focus','Motivation','Stress Control','Fatigue Control','Breathing'],
    datasets:[{{
      label:'Athlete Profile',
      data:[
        {summary.get('avg_wellness',0)},
        {summary.get('avg_form',0)},
        {summary.get('avg_focus',0)},
        {summary.get('avg_motivation',0)},
        {round(100-summary.get('avg_stress',50),1)},
        {round(100-summary.get('avg_fatigue',50),1)},
        60
      ],
      borderColor:'#3b82f6',backgroundColor:'#3b82f622',pointBackgroundColor:'#3b82f6'
    }}]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{labels:{{color:'#94a3b8'}}}}}},
    scales:{{r:{{min:0,max:100,ticks:{{color:'#64748b',backdropColor:'transparent'}},
      grid:{{color:'#334155'}},pointLabels:{{color:'#94a3b8'}}}}}}
  }}
}});

// Per-rep chart
if(repLabels.length>0){{
  new Chart(document.getElementById('repChart'),{{
    type:'bar',
    data:{{
      labels:repLabels,
      datasets:[
        {{label:'Form %',data:repForm,backgroundColor:'#10b981aa'}},
        {{label:'Focus %',data:repFocus,backgroundColor:'#22d3eeaa'}},
        {{label:'Fatigue %',data:repFatigue,backgroundColor:'#f59e0baa'}}
      ]
    }},
    options:{{...chartDefaults,plugins:{{...chartDefaults.plugins,
      legend:{{labels:{{color:'#94a3b8'}}}}}}}}
  }});
}} else {{
  document.getElementById('repChart').parentElement.innerHTML += '<p style="color:#64748b;text-align:center;padding:40px">Complete at least one rep to see per-rep data</p>';
}}
</script>

</body>
</html>"""
        return html

    # ──────────────────────────────────────────────────────────────────────────
    def get_statistics(self) -> dict:
        return {
            'total_frames':        self.total_frames,
            'adjustment_count':    self.adjustment_count,
            'adjustment_frequency':round(self.adjustment_count / max(self.total_frames,1) * 100, 1),
            'history_size':        len(self.history_buffer),
            'session_duration':    round(time.time() - self.session_start, 1)
        }

    def reset(self):
        self.prev_wellness   = None
        self.history_buffer.clear()
        self.session_log     = []
        self.rep_log         = []
        self.event_log       = []
        self.adjustment_count= 0
        self.total_frames    = 0
        self._prev_rep_count = 0
        self.session_start   = time.time()
        self.session_id      = datetime.now().strftime('%Y%m%d_%H%M%S')
