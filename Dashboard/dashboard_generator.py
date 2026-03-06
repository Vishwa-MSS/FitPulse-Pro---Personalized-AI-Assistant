"""
dashboard_generator.py
======================
ACPF Interactive Dashboard Generator for FitPulse Pro

Standalone module that takes a completed session summary dict
and generates a fully self-contained interactive HTML dashboard
with Chart.js visualisations for Strength & Conditioning analysis.

Usage (from app.py or acpf_algorithm.py):
    from dashboard.dashboard_generator import DashboardGenerator
    gen  = DashboardGenerator(session_summary)
    html = gen.generate()

Or use the convenience function:
    html = generate_dashboard(session_summary)
"""

import json
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# HELPER UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _grade(score: float) -> tuple:
    """Returns (letter, emoji, hex_color) grade for a 0–100 score."""
    if score >= 80: return ('A', '🏆', '#10b981')
    if score >= 65: return ('B', '✅', '#22d3ee')
    if score >= 50: return ('C', '⚠️', '#f59e0b')
    return ('D', '⛔', '#ef4444')


def _safe(val, fallback=0):
    """Return val if truthy numeric, else fallback."""
    try:
        return round(float(val), 1)
    except Exception:
        return fallback


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD GENERATOR CLASS
# ══════════════════════════════════════════════════════════════════════════════

class DashboardGenerator:
    """
    Generates a fully self-contained interactive HTML dashboard
    from an ACPF session summary dictionary.

    The output HTML:
      - Requires NO internet connection to view (Chart.js loaded from CDN,
        but all session data is embedded as JSON in <script> tags)
      - Can be printed to PDF via browser's Print dialog
      - Works on any device / browser

    Args:
        session_summary (dict): Output of ACPFAlgorithm.get_session_summary()
    """

    def __init__(self, session_summary: dict):
        self.s = session_summary

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD
    # ──────────────────────────────────────────────────────────────────────────
    def generate(self) -> str:
        """
        Generate the full HTML dashboard string.

        Returns:
            str: Complete self-contained HTML file content
        """
        s        = self.s
        timeline = s.get('timeline', [])
        rep_log  = s.get('rep_log', [])
        events   = s.get('event_log', [])

        # ── Extract time-series arrays ─────────────────────────────────────
        labels        = [_safe(e.get('elapsed'),  0) for e in timeline]
        wellness_ts   = [_safe(e.get('wellness'), 0) for e in timeline]
        acpf_ts       = [_safe(e.get('acpf_score'), 0) for e in timeline]
        form_ts       = [_safe(e.get('form'),     0) for e in timeline]
        focus_ts      = [_safe(e.get('focus'),    0) for e in timeline]
        fatigue_ts    = [_safe(e.get('fatigue'),  0) for e in timeline]
        stress_ts     = [_safe(e.get('stress'),   0) for e in timeline]
        motivation_ts = [_safe(e.get('motivation'),0) for e in timeline]
        breathing_ts  = [_safe(e.get('breathing'),0) for e in timeline]

        # ── Per-rep arrays ─────────────────────────────────────────────────
        rep_labels   = [f"Rep {r.get('rep_num', i+1)}" for i, r in enumerate(rep_log)]
        rep_form     = [_safe(r.get('form'),    0) for r in rep_log]
        rep_fatigue  = [_safe(r.get('fatigue'), 0) for r in rep_log]
        rep_focus    = [_safe(r.get('focus'),   0) for r in rep_log]
        rep_wellness = [_safe(r.get('wellness'),0) for r in rep_log]
        rep_angles   = [_safe(r.get('angle'),   0) for r in rep_log]

        # ── Grades ─────────────────────────────────────────────────────────
        well_grade  = _grade(s.get('avg_wellness', 0))
        form_grade  = _grade(s.get('avg_form',     0))
        acpf_grade  = _grade(s.get('avg_acpf',     0))
        focus_grade = _grade(s.get('avg_focus',    0))
        mot_grade   = _grade(s.get('avg_motivation',0))

        # ── Radar data ─────────────────────────────────────────────────────
        radar_data = [
            _safe(s.get('avg_wellness',   0)),
            _safe(s.get('avg_form',       0)),
            _safe(s.get('avg_focus',      0)),
            _safe(s.get('avg_motivation', 0)),
            round(100 - _safe(s.get('avg_stress',  50)), 1),
            round(100 - _safe(s.get('avg_fatigue', 50)), 1),
            60   # placeholder breathing quality
        ]

        # ── HTML tables ────────────────────────────────────────────────────
        events_rows = self._build_events_table(events)
        rep_rows    = self._build_rep_table(rep_log)

        # ── Render ─────────────────────────────────────────────────────────
        return self._render_html(
            s=s,
            labels=labels,
            wellness_ts=wellness_ts, acpf_ts=acpf_ts,
            form_ts=form_ts, focus_ts=focus_ts,
            fatigue_ts=fatigue_ts, stress_ts=stress_ts,
            motivation_ts=motivation_ts, breathing_ts=breathing_ts,
            rep_labels=rep_labels, rep_form=rep_form,
            rep_fatigue=rep_fatigue, rep_focus=rep_focus,
            rep_wellness=rep_wellness, rep_angles=rep_angles,
            radar_data=radar_data,
            well_grade=well_grade, form_grade=form_grade,
            acpf_grade=acpf_grade, focus_grade=focus_grade,
            mot_grade=mot_grade,
            events_rows=events_rows,
            rep_rows=rep_rows
        )

    # ──────────────────────────────────────────────────────────────────────────
    # TABLE BUILDERS
    # ──────────────────────────────────────────────────────────────────────────
    def _build_events_table(self, events: list) -> str:
        if not events:
            return ('<tr><td colspan="3" style="text-align:center;color:#10b981;">'
                    '✅ No critical events — excellent session!</td></tr>')
        rows = []
        for ev in events:
            rows.append(
                f'<tr>'
                f'<td>{_safe(ev.get("elapsed"),0)}s</td>'
                f'<td><span class="badge badge-stop">{ev.get("event","EVENT")}</span></td>'
                f'<td>{ev.get("detail","—")}</td>'
                f'</tr>'
            )
        return ''.join(rows)

    def _build_rep_table(self, rep_log: list) -> str:
        if not rep_log:
            return ('<tr><td colspan="7" style="text-align:center;color:#6b7280;">'
                    'No reps recorded in this session</td></tr>')
        rows = []
        for r in rep_log:
            form_val = _safe(r.get('form'), 0)
            form_color = _grade(form_val)[2]
            rows.append(
                f'<tr>'
                f'<td><strong>Rep {r.get("rep_num","?")}</strong></td>'
                f'<td>{_safe(r.get("elapsed"),0)}s</td>'
                f'<td style="color:{form_color};font-weight:700;">{form_val}%</td>'
                f'<td>{_safe(r.get("angle"),0)}°</td>'
                f'<td>{r.get("emotion","—")}</td>'
                f'<td>{_safe(r.get("fatigue"),0)}%</td>'
                f'<td>{_safe(r.get("focus"),0)}%</td>'
                f'</tr>'
            )
        return ''.join(rows)

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN HTML RENDERER
    # ──────────────────────────────────────────────────────────────────────────
    def _render_html(self, s, labels, wellness_ts, acpf_ts, form_ts, focus_ts,
                     fatigue_ts, stress_ts, motivation_ts, breathing_ts,
                     rep_labels, rep_form, rep_fatigue, rep_focus,
                     rep_wellness, rep_angles, radar_data,
                     well_grade, form_grade, acpf_grade, focus_grade, mot_grade,
                     events_rows, rep_rows) -> str:

        athlete_name   = s.get('athlete_name', 'Athlete')
        exercise       = s.get('exercise', 'N/A')
        ex_type        = s.get('exercise_type', 'strength').title()
        date_str       = s.get('date', datetime.now().strftime('%Y-%m-%d %H:%M'))
        session_id     = s.get('session_id', 'N/A')
        duration_fmt   = s.get('duration_formatted', 'N/A')
        total_reps     = s.get('total_reps', 0)
        adj_count      = s.get('adjustment_count', 0)

        avg_wellness   = _safe(s.get('avg_wellness',   0))
        avg_form       = _safe(s.get('avg_form',       0))
        avg_focus      = _safe(s.get('avg_focus',      0))
        avg_fatigue    = _safe(s.get('avg_fatigue',    0))
        avg_stress     = _safe(s.get('avg_stress',     0))
        avg_breathing  = _safe(s.get('avg_breathing',  0))
        avg_motivation = _safe(s.get('avg_motivation', 0))
        avg_acpf       = _safe(s.get('avg_acpf',       0))
        peak_wellness  = _safe(s.get('peak_wellness',  0))
        peak_form      = _safe(s.get('peak_form',      0))
        peak_motivation= _safe(s.get('peak_motivation',0))

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>ACPF Dashboard — {athlete_name} — {date_str}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}

/* ── Header ── */
.header{{
  background:linear-gradient(135deg,#1e40af,#7c3aed);
  padding:28px 40px;display:flex;align-items:center;
  justify-content:space-between;flex-wrap:wrap;gap:16px;
}}
.header h1{{font-size:26px;font-weight:800;color:#fff}}
.header h1 span{{color:#fbbf24}}
.header-meta{{color:rgba(255,255,255,0.8);font-size:14px;line-height:2;margin-top:6px}}
.header-badges{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.badge-pill{{
  background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.25);
  border-radius:20px;padding:6px 14px;color:#fff;font-size:12px;font-weight:600;
  backdrop-filter:blur(4px);
}}
.print-btn{{
  background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);
  color:#fff;padding:10px 20px;border-radius:10px;font-size:14px;font-weight:700;
  cursor:pointer;transition:background .2s;
}}
.print-btn:hover{{background:rgba(255,255,255,0.3)}}

/* ── Layout ── */
.container{{max-width:1400px;margin:0 auto;padding:28px 24px}}
.section-title{{
  font-size:18px;font-weight:700;color:#f1f5f9;
  margin:32px 0 16px;display:flex;align-items:center;gap:10px;
}}
.section-title::before{{
  content:'';display:block;width:4px;height:22px;
  background:linear-gradient(#3b82f6,#8b5cf6);border-radius:2px;
}}

/* ── ACPF Banner ── */
.acpf-banner{{
  background:linear-gradient(135deg,#1e3a8a1a,#6d28d91a);
  border:1px solid #3b82f633;border-radius:16px;
  padding:32px;margin-bottom:28px;text-align:center;
}}
.acpf-score-num{{
  font-size:80px;font-weight:900;line-height:1;
  background:linear-gradient(135deg,#3b82f6,#8b5cf6);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}}
.acpf-score-label{{
  font-size:13px;color:#64748b;margin-top:8px;
  text-transform:uppercase;letter-spacing:2px;
}}
.acpf-desc{{
  font-size:14px;color:#94a3b8;margin-top:14px;
  max-width:640px;margin-inline:auto;line-height:1.7;
}}

/* ── Metric Cards ── */
.cards{{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(155px,1fr));
  gap:14px;margin-bottom:28px;
}}
.card{{
  background:#1e293b;border:1px solid #334155;
  border-radius:14px;padding:18px;text-align:center;
  transition:transform .2s,border-color .2s;
}}
.card:hover{{transform:translateY(-2px);border-color:#475569}}
.card-icon{{font-size:26px;margin-bottom:8px}}
.card-label{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:5px;font-weight:600}}
.card-value{{font-size:24px;font-weight:800;margin-bottom:3px}}
.card-sub{{font-size:12px;color:#94a3b8}}

/* ── Chart Grid ── */
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:28px}}
.chart-grid.full{{grid-template-columns:1fr}}
.chart-card{{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:22px}}
.chart-card h3{{font-size:13px;font-weight:600;color:#64748b;margin-bottom:14px;text-transform:uppercase;letter-spacing:.5px}}
.chart-wrapper{{position:relative;height:260px}}

/* ── Table ── */
.table-card{{background:#1e293b;border:1px solid #334155;border-radius:14px;overflow:hidden;margin-bottom:28px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#0f172a;color:#64748b;text-transform:uppercase;font-size:10px;letter-spacing:.5px;padding:12px 16px;text-align:left;font-weight:600}}
td{{padding:11px 16px;border-bottom:1px solid #0f172a;color:#cbd5e1}}
tr:hover td{{background:#243044}}
tr:last-child td{{border-bottom:none}}

/* ── Badges ── */
.badge{{padding:2px 10px;border-radius:20px;font-size:10px;font-weight:700}}
.badge-stop{{background:#7f1d1d;color:#fca5a5}}
.badge-safe{{background:#14532d;color:#86efac}}
.badge-caution{{background:#78350f;color:#fde68a}}

/* ── Innovation box ── */
.innovation-box{{
  background:linear-gradient(135deg,#1e3a8a12,#6d28d912);
  border:1px solid #3b82f625;border-radius:14px;padding:24px;
  margin-bottom:28px;
}}
.innovation-box h3{{color:#93c5fd;font-size:16px;margin-bottom:10px}}
.innovation-box p{{color:#94a3b8;line-height:1.8;font-size:13px}}

/* ── Footer ── */
.footer{{
  text-align:center;padding:24px;color:#475569;
  font-size:12px;border-top:1px solid #1e293b;margin-top:24px;
}}

/* ── Print styles ── */
@media print{{
  body{{background:#fff;color:#000}}
  .header{{background:#1e40af;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  .card,.chart-card,.table-card,.acpf-banner,.innovation-box{{
    border:1px solid #ccc;background:#f9fafb;
    -webkit-print-color-adjust:exact;print-color-adjust:exact;
  }}
  .print-btn{{display:none}}
}}

@media(max-width:768px){{
  .chart-grid{{grid-template-columns:1fr}}
  .cards{{grid-template-columns:repeat(2,1fr)}}
  .acpf-score-num{{font-size:56px}}
  .header{{padding:20px}}
}}
</style>
</head>
<body>

<!-- ════ HEADER ════════════════════════════════════════════════════════════ -->
<div class="header">
  <div>
    <h1>💪 FitPulse Pro — <span>ACPF Dashboard</span></h1>
    <div class="header-meta">
      Athlete: <strong>{athlete_name}</strong> &nbsp;|&nbsp;
      Exercise: <strong>{exercise}</strong> &nbsp;|&nbsp;
      Type: <strong>{ex_type}</strong><br/>
      Date: <strong>{date_str}</strong> &nbsp;|&nbsp;
      Session ID: <code style="font-size:12px;opacity:.7">{session_id}</code>
    </div>
  </div>
  <div class="header-badges">
    <span class="badge-pill">⏱ {duration_fmt}</span>
    <span class="badge-pill">🔁 {total_reps} Reps</span>
    <span class="badge-pill">⚡ {adj_count} Adaptations</span>
    <button class="print-btn" onclick="window.print()">🖨️ Print / Save PDF</button>
  </div>
</div>

<div class="container">

  <!-- ════ ACPF COMPOSITE SCORE ═══════════════════════════════════════════ -->
  <div class="section-title">ACPF Composite Score</div>
  <div class="acpf-banner">
    <div class="acpf-score-num">{avg_acpf}</div>
    <div class="acpf-score-label">/ 100 &nbsp;·&nbsp; Adaptive Cognitive-Physical Fusion Score</div>
    <div class="acpf-desc">
      The ACPF Score fuses physical form quality, cognitive state, and dynamically
      adapted attention weights into a single performance index.
      Session Grade: <strong style="color:{acpf_grade[2]}">{acpf_grade[0]} {acpf_grade[1]}</strong>
    </div>
  </div>

  <!-- ════ KEY METRICS CARDS ══════════════════════════════════════════════ -->
  <div class="section-title">Session Metrics Overview</div>
  <div class="cards">
    <div class="card">
      <div class="card-icon">🧘</div>
      <div class="card-label">Avg Wellness</div>
      <div class="card-value" style="color:{well_grade[2]}">{avg_wellness}%</div>
      <div class="card-sub">Peak {peak_wellness}% &nbsp; Grade {well_grade[0]}</div>
    </div>
    <div class="card">
      <div class="card-icon">🎯</div>
      <div class="card-label">Avg Form</div>
      <div class="card-value" style="color:{form_grade[2]}">{avg_form}%</div>
      <div class="card-sub">Peak {peak_form}% &nbsp; Grade {form_grade[0]}</div>
    </div>
    <div class="card">
      <div class="card-icon">👁️</div>
      <div class="card-label">Avg Focus</div>
      <div class="card-value" style="color:{focus_grade[2]}">{avg_focus}%</div>
      <div class="card-sub">Gaze Score &nbsp; Grade {focus_grade[0]}</div>
    </div>
    <div class="card">
      <div class="card-icon">😴</div>
      <div class="card-label">Avg Fatigue</div>
      <div class="card-value" style="color:#f59e0b">{avg_fatigue}%</div>
      <div class="card-sub">Lower is better</div>
    </div>
    <div class="card">
      <div class="card-icon">😤</div>
      <div class="card-label">Avg Stress</div>
      <div class="card-value" style="color:#f97316">{avg_stress}%</div>
      <div class="card-sub">Lower is better</div>
    </div>
    <div class="card">
      <div class="card-icon">🫁</div>
      <div class="card-label">Avg Breathing</div>
      <div class="card-value" style="color:#a78bfa">{avg_breathing}</div>
      <div class="card-sub">Breaths per minute</div>
    </div>
    <div class="card">
      <div class="card-icon">🔥</div>
      <div class="card-label">Avg Motivation</div>
      <div class="card-value" style="color:{mot_grade[2]}">{avg_motivation}%</div>
      <div class="card-sub">Peak {peak_motivation}% &nbsp; Grade {mot_grade[0]}</div>
    </div>
    <div class="card">
      <div class="card-icon">⚡</div>
      <div class="card-label">Weight Shifts</div>
      <div class="card-value" style="color:#e879f9">{adj_count}</div>
      <div class="card-sub">ACPF adaptations</div>
    </div>
  </div>

  <!-- ════ TIME SERIES CHARTS ═════════════════════════════════════════════ -->
  <div class="section-title">Real-Time Performance Timeline</div>
  <div class="chart-grid">
    <div class="chart-card">
      <h3>🧘 Wellness + ACPF Score Over Time</h3>
      <div class="chart-wrapper"><canvas id="wellnessChart"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>🎯 Form + Focus Over Time</h3>
      <div class="chart-wrapper"><canvas id="formFocusChart"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>😴 Fatigue + Stress Over Time</h3>
      <div class="chart-wrapper"><canvas id="fatigueStressChart"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>🫁 Breathing Rate + Motivation Over Time</h3>
      <div class="chart-wrapper"><canvas id="breathingChart"></canvas></div>
    </div>
  </div>

  <!-- ════ RADAR + PER-REP CHARTS ═════════════════════════════════════════ -->
  <div class="chart-grid">
    <div class="chart-card">
      <h3>📊 Athlete Performance Radar</h3>
      <div class="chart-wrapper"><canvas id="radarChart"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>🔁 Per-Rep Quality Breakdown</h3>
      <div class="chart-wrapper"><canvas id="repChart"></canvas></div>
    </div>
  </div>

  <!-- ════ JOINT ANGLE CHART ══════════════════════════════════════════════ -->
  <div class="section-title">Joint Angle Per Rep</div>
  <div class="chart-grid full">
    <div class="chart-card">
      <h3>📐 Joint Angle Across All Reps</h3>
      <div class="chart-wrapper"><canvas id="angleChart"></canvas></div>
    </div>
  </div>

  <!-- ════ REP-BY-REP TABLE ═══════════════════════════════════════════════ -->
  <div class="section-title">Rep-by-Rep Breakdown</div>
  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th>Rep</th><th>Time</th><th>Form %</th>
          <th>Angle</th><th>Emotion</th><th>Fatigue %</th><th>Focus %</th>
        </tr>
      </thead>
      <tbody>{rep_rows}</tbody>
    </table>
  </div>

  <!-- ════ CRITICAL EVENTS LOG ════════════════════════════════════════════ -->
  <div class="section-title">Critical Events Log</div>
  <div class="table-card">
    <table>
      <thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead>
      <tbody>{events_rows}</tbody>
    </table>
  </div>

  <!-- ════ ACPF INNOVATION EXPLANATION ════════════════════════════════════ -->
  <div class="section-title">About the ACPF Algorithm</div>
  <div class="innovation-box">
    <h3>⚙️ Adaptive Cognitive-Physical Fusion (ACPF) — Algorithm Overview</h3>
    <p>
      ACPF is a real-time multi-modal fusion algorithm for intelligent athletic performance monitoring.
      Unlike static weighted-average systems, ACPF <strong style="color:#93c5fd">dynamically adjusts 
      its 7-dimensional attention weights at every frame</strong> based on threshold-crossing rules 
      across form score, range of motion, movement smoothness, focus (gaze), fatigue, stress, 
      and breathing rate.
      <br/><br/>
      <strong style="color:#fbbf24">Key innovation:</strong> When a critical condition is detected 
      (e.g. fatigue &gt; 70%, poor form &lt; 55%, low focus &lt; 45%), the relevant dimension's 
      weight is boosted and safety-critical signals are prioritised — giving athletes real-time 
      adaptive coaching intelligence rather than one-size-fits-all feedback.
      <br/><br/>
      During this session, ACPF made 
      <strong style="color:#e879f9">{adj_count} adaptive weight adjustments</strong>, 
      ensuring the most relevant signal was always prioritised at the right moment.
    </p>
  </div>

</div><!-- end .container -->

<div class="footer">
  Generated by <strong>FitPulse Pro — ACPF Cognitive Fitness System</strong> &nbsp;|&nbsp;
  Session ID: {session_id} &nbsp;|&nbsp; {date_str}
</div>

<!-- ════ CHART.JS SCRIPTS ══════════════════════════════════════════════════ -->
<script>
// ── Embedded session data ─────────────────────────────────────────────────
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
const repAngles     = {json.dumps(rep_angles)};
const radarData     = {json.dumps(radar_data)};

// ── Shared chart defaults ─────────────────────────────────────────────────
const sharedScales = {{
  x: {{
    ticks: {{ color:'#64748b', maxTicksLimit:10 }},
    grid:  {{ color:'#1e293b55' }},
    title: {{ display:true, text:'Elapsed (seconds)', color:'#64748b', font:{{size:11}} }}
  }},
  y: {{
    ticks: {{ color:'#64748b' }},
    grid:  {{ color:'#1e293b55' }},
    min: 0, max: 100
  }}
}};
const sharedPlugins = {{
  legend: {{ labels: {{ color:'#94a3b8', font:{{size:12}}, boxWidth:12 }} }},
  tooltip: {{ backgroundColor:'#1e293b', titleColor:'#e2e8f0', bodyColor:'#94a3b8', borderColor:'#334155', borderWidth:1 }}
}};

function lineOpts(extraScales) {{
  return {{
    responsive:true, maintainAspectRatio:false,
    plugins: sharedPlugins,
    scales: Object.assign({{}}, sharedScales, extraScales || {{}})
  }};
}}

// ── 1. Wellness + ACPF ───────────────────────────────────────────────────
new Chart(document.getElementById('wellnessChart'), {{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{ label:'Wellness %', data:wellnessTS, borderColor:'#3b82f6',
         backgroundColor:'#3b82f615', tension:.4, fill:true, pointRadius:0, borderWidth:2 }},
      {{ label:'ACPF Score', data:acpfTS, borderColor:'#8b5cf6',
         backgroundColor:'#8b5cf615', tension:.4, fill:true, pointRadius:0, borderWidth:2 }}
    ]
  }},
  options: lineOpts()
}});

// ── 2. Form + Focus ───────────────────────────────────────────────────────
new Chart(document.getElementById('formFocusChart'), {{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{ label:'Form %',  data:formTS,  borderColor:'#10b981', tension:.4, pointRadius:0, borderWidth:2 }},
      {{ label:'Focus %', data:focusTS, borderColor:'#22d3ee', tension:.4, pointRadius:0, borderWidth:2 }}
    ]
  }},
  options: lineOpts()
}});

// ── 3. Fatigue + Stress ───────────────────────────────────────────────────
new Chart(document.getElementById('fatigueStressChart'), {{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{ label:'Fatigue %', data:fatigueTS, borderColor:'#f59e0b', tension:.4, pointRadius:0, borderWidth:2 }},
      {{ label:'Stress %',  data:stressTS,  borderColor:'#ef4444', tension:.4, pointRadius:0, borderWidth:2 }}
    ]
  }},
  options: lineOpts()
}});

// ── 4. Breathing + Motivation ─────────────────────────────────────────────
new Chart(document.getElementById('breathingChart'), {{
  type:'line',
  data:{{
    labels,
    datasets:[
      {{ label:'Breathing (BPM)', data:breathingTS, borderColor:'#a78bfa',
         tension:.4, pointRadius:0, borderWidth:2, yAxisID:'bpm' }},
      {{ label:'Motivation %',    data:motivationTS, borderColor:'#fb923c',
         tension:.4, pointRadius:0, borderWidth:2 }}
    ]
  }},
  options:{{
    responsive:true, maintainAspectRatio:false,
    plugins: sharedPlugins,
    scales:{{
      x: sharedScales.x,
      y: {{ ...sharedScales.y, position:'left',  title:{{display:true,text:'%',color:'#64748b'}} }},
      bpm: {{
        position:'right', min:0, max:50,
        ticks:{{ color:'#a78bfa' }},
        grid:{{ display:false }},
        title:{{ display:true, text:'BPM', color:'#a78bfa', font:{{size:11}} }}
      }}
    }}
  }}
}});

// ── 5. Radar ──────────────────────────────────────────────────────────────
new Chart(document.getElementById('radarChart'), {{
  type:'radar',
  data:{{
    labels:['Wellness','Form','Focus','Motivation','Stress Ctrl','Fatigue Ctrl','Breathing'],
    datasets:[{{
      label: 'Athlete Profile',
      data: radarData,
      borderColor:'#3b82f6', backgroundColor:'#3b82f622',
      pointBackgroundColor:'#3b82f6', pointRadius:4, borderWidth:2
    }}]
  }},
  options:{{
    responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{ labels:{{ color:'#94a3b8' }} }} }},
    scales:{{
      r:{{
        min:0, max:100,
        ticks:{{ color:'#64748b', backdropColor:'transparent', stepSize:20 }},
        grid:{{ color:'#334155' }},
        pointLabels:{{ color:'#94a3b8', font:{{size:11}} }}
      }}
    }}
  }}
}});

// ── 6. Per-rep bar chart ───────────────────────────────────────────────────
if (repLabels.length > 0) {{
  new Chart(document.getElementById('repChart'), {{
    type:'bar',
    data:{{
      labels: repLabels,
      datasets:[
        {{ label:'Form %',    data:repForm,    backgroundColor:'#10b98199' }},
        {{ label:'Focus %',   data:repFocus,   backgroundColor:'#22d3ee99' }},
        {{ label:'Fatigue %', data:repFatigue, backgroundColor:'#f59e0b99' }}
      ]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      plugins: sharedPlugins,
      scales:{{
        x:{{ ticks:{{color:'#64748b'}}, grid:{{color:'#1e293b55'}} }},
        y:{{ ticks:{{color:'#64748b'}}, grid:{{color:'#1e293b55'}}, min:0, max:100 }}
      }}
    }}
  }});
}} else {{
  const c = document.getElementById('repChart');
  c.parentElement.innerHTML += '<p style="color:#64748b;text-align:center;padding:40px 0">Complete at least one rep to see per-rep data</p>';
}}

// ── 7. Angle chart ────────────────────────────────────────────────────────
if (repLabels.length > 0) {{
  new Chart(document.getElementById('angleChart'), {{
    type:'line',
    data:{{
      labels: repLabels,
      datasets:[{{
        label:'Joint Angle (°)',
        data: repAngles,
        borderColor:'#e879f9', backgroundColor:'#e879f915',
        tension:.4, fill:true, pointRadius:5,
        pointBackgroundColor:'#e879f9', borderWidth:2
      }}]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      plugins: sharedPlugins,
      scales:{{
        x:{{ ticks:{{color:'#64748b'}}, grid:{{color:'#1e293b55'}} }},
        y:{{ ticks:{{color:'#64748b'}}, grid:{{color:'#1e293b55'}}, min:0, max:180,
             title:{{display:true, text:'Degrees (°)', color:'#64748b'}} }}
      }}
    }}
  }});
}} else {{
  const c = document.getElementById('angleChart');
  c.parentElement.innerHTML += '<p style="color:#64748b;text-align:center;padding:40px 0">No angle data yet</p>';
}}
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def generate_dashboard(session_summary: dict) -> str:
    """
    Convenience wrapper — generate dashboard HTML from a session summary dict.

    Args:
        session_summary (dict): From ACPFAlgorithm.get_session_summary()

    Returns:
        str: Self-contained HTML string
    """
    return DashboardGenerator(session_summary).generate()


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import time

    # Build a mock session summary to test rendering
    mock_timeline = []
    for i in range(60):
        mock_timeline.append({
            'elapsed':    i * 2,
            'wellness':   60 + 15 * (i / 60),
            'acpf_score': 58 + 18 * (i / 60),
            'form':       70 + 10 * (i / 60),
            'focus':      65 + 8  * (i / 60),
            'fatigue':    10 + 30 * (i / 60),
            'stress':     25 + 10 * (i / 60),
            'motivation': 75 - 5  * (i / 60),
            'breathing':  15 + 3  * (i / 60),
        })

    mock_rep_log = [
        {'rep_num':i+1, 'elapsed':(i+1)*12, 'form':72+i*2, 'angle':145-i*3,
         'emotion':'Happy' if i%2==0 else 'Neutral', 'fatigue':10+i*4, 'focus':75-i}
        for i in range(8)
    ]

    mock_summary = {
        'session_id':       '20260222_164500',
        'athlete_name':     'Test Athlete',
        'exercise':         'Bicep Curl',
        'exercise_type':    'strength',
        'date':             datetime.now().strftime('%Y-%m-%d %H:%M'),
        'duration_formatted':'4m 30s',
        'total_reps':       8,
        'avg_wellness':     71.2,
        'avg_form':         78.5,
        'avg_focus':        68.3,
        'avg_fatigue':      32.1,
        'avg_stress':       28.4,
        'avg_breathing':    16.2,
        'avg_motivation':   72.0,
        'avg_acpf':         69.8,
        'peak_wellness':    85.1,
        'peak_form':        92.0,
        'peak_motivation':  88.0,
        'adjustment_count': 14,
        'rep_log':          mock_rep_log,
        'event_log':        [],
        'timeline':         mock_timeline
    }

    html   = generate_dashboard(mock_summary)
    outfile= 'test_dashboard_output.html'
    with open(outfile, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ Test dashboard generated: {outfile}")
    print(f"   Open in your browser to preview.")