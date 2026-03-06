"""
╔══════════════════════════════════════════════════════════════════════════════╗
║       MODULE 3 — COGNITIVE & PHYSICAL STATE FUSION : ACPF ALGORITHM        ║
║       FitPulse Pro  |  Cognitive-Physical Fitness System                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

DESCRIPTION:
    Demonstrates the ACPF (Adaptive Cognitive-Physical Fusion) algorithm
    using a simulated 20-rep Bicep Curl session.

    NO CAMERA REQUIRED. Runs entirely in the terminal.

    Simulates realistic signal evolution:
      • Form degrades ~18% by final rep (fatigue effect)
      • Focus dips mid-session then partially recovers
      • Fatigue builds gradually, accelerates after rep 12
      • Stress rises mid-session then drops
      • Emotion: Happy → Neutral → Angry (effort) → Happy (finish)
      • Breathing rate rises with effort

    OUTPUT — all printed to terminal + saved to files:
      Section 1 : Session configuration
      Section 2 : ACPF base weight profile (bar chart)
      Section 3 : Rep-by-rep detailed tables
                    — Physical inputs (angle, form, ROM, smoothness)
                    — Cognitive inputs (focus, fatigue, stress, breathing, emotion)
                    — ACPF fusion output (physical%, cognitive%, wellness%, ACPF%)
                    — Dynamic weight adjustment log
      Section 4 : ASCII bar charts (wellness, ACPF, fatigue, focus per rep)
      Section 4b: Attention weight evolution across key reps
      Section 5 : Session summary statistics with grade & bar chart
      Section 6 : ACPF algorithm explanation (ready to paste in report)

    Saves:
      output/mod3_acpf_report_<ts>.txt    — full text report
      output/acpf_dashboard_<ts>.html     — interactive Chart.js dashboard

RUN:
    python module3_acpf_algorithm.py
"""

import sys
import os
import math
import time
import random
import numpy as np
from datetime import datetime

# ── Path setup ─────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cognitive"))

from cognitive.acpf_algorithm import (
    ACPFAlgorithm, PhysicalState, CognitiveState,
    ExerciseType, RiskLevel
)

os.makedirs("output", exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
#  TERMINAL FORMATTING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

W = 82   # terminal width

def dline():   return "=" * W
def sline():   return "-" * W

def section(title):
    return "\n" + sline() + "\n  " + title + "\n" + sline()

def bar_chart(value, max_val=100, width=30, fill="#", empty="."):
    """Simple ASCII bar e.g.  ###########................."""
    value    = float(value)
    max_val  = float(max_val)
    filled   = int(round(value / max_val * width))
    filled   = max(0, min(filled, width))
    return fill * filled + empty * (width - filled)

def sparkline(values, width=40, lo=0.0, hi=100.0):
    """
    Returns a string of block characters representing value trend.
    Uses: _ . - = ^ ~ # (7 levels, no unicode needed)
    """
    chars = " _.-=^~#"
    if not values:
        return " " * width
    n       = len(values)
    sampled = []
    for i in range(width):
        idx = int(i * n / width)
        sampled.append(values[min(idx, n-1)])
    result = ""
    lo, hi = float(lo), float(hi)
    for v in sampled:
        idx = int((v - lo) / max(hi - lo, 1.0) * (len(chars)-1))
        idx = max(0, min(len(chars)-1, idx))
        result += chars[idx]
    return result

def risk_label(risk_value):
    return {"SAFE": "SAFE   ", "CAUTION": "CAUTION", "STOP": "STOP   "}.get(risk_value, risk_value)

def grade(score):
    score = float(score)
    if score >= 80: return "A  [Excellent]"
    if score >= 65: return "B  [Good]     "
    if score >= 50: return "C  [Moderate] "
    return                  "D  [Poor]     "

# ══════════════════════════════════════════════════════════════════════════════
#  REALISTIC SESSION SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def simulate_session(n_reps=20, seed=42):
    random.seed(seed)
    np.random.seed(seed)

    emotion_seq = (
        ["Happy"]   * 4 +
        ["Neutral"] * 5 +
        ["Angry"]   * 4 +
        ["Neutral"] * 4 +
        ["Happy"]   * 3
    )

    reps = []
    for i in range(n_reps):
        t      = i / max(n_reps - 1, 1)
        emotion = emotion_seq[min(i, len(emotion_seq)-1)]

        angle           = float(np.clip(35 + t*25 + np.random.normal(0, 4), 20, 80))
        form_score      = float(np.clip(92 - t*18 + np.random.normal(0, 4), 45, 100))
        range_of_motion = float(np.clip(88 - t*12 + np.random.normal(0, 5), 40, 100))
        smoothness      = float(np.clip(85 - t*20 + np.random.normal(0, 6), 35, 100))

        focus_curve     = 80 - 25 * math.sin(math.pi * t)
        focus_score     = float(np.clip(focus_curve + np.random.normal(0, 5), 20, 98))

        fatigue_base    = t * 72 + max(0.0, (i - 12) * 2.0)
        fatigue_level   = float(np.clip(fatigue_base + np.random.normal(0, 4), 0, 95))

        stress_curve    = 20 + 50 * math.sin(math.pi * t * 0.9)
        stress_index    = float(np.clip(stress_curve + np.random.normal(0, 5), 10, 90))

        breathing_rate  = float(np.clip(12 + t*10 + np.random.normal(0, 1), 10, 30))

        motiv_base      = {"Happy":85,"Neutral":65,"Angry":72,"Sad":35,"Fear":30}.get(emotion, 60)
        motivation      = float(np.clip(motiv_base + np.random.normal(0, 6), 20, 100))

        reps.append({
            "rep_num"         : i + 1,
            "angle"           : angle,
            "form_score"      : form_score,
            "range_of_motion" : range_of_motion,
            "smoothness"      : smoothness,
            "focus_score"     : focus_score,
            "fatigue_level"   : fatigue_level,
            "stress_index"    : stress_index,
            "breathing_rate"  : breathing_rate,
            "emotion"         : emotion,
            "motivation"      : motivation,
        })
    return reps

# ══════════════════════════════════════════════════════════════════════════════
#  REPORT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_report(results, summary, acpf, exercise, ex_type, n_reps, athlete):
    out = []

    # ── Header ─────────────────────────────────────────────────────────────────
    out.append(dline())
    out.append("  FitPulse Pro -- ACPF Algorithm Demo Report".center(W))
    out.append("  Adaptive Cognitive-Physical Fusion (ACPF)".center(W))
    out.append(("  Generated: " + datetime.now().strftime("%Y-%m-%d  %H:%M:%S")).center(W))
    out.append(dline())

    # ── Section 1 ──────────────────────────────────────────────────────────────
    out.append(section("SECTION 1 -- SESSION CONFIGURATION"))
    out.append("  Exercise         : " + exercise)
    out.append("  Exercise Type    : " + ex_type)
    out.append("  Total Reps       : " + str(n_reps))
    out.append("  Smoothing Factor : 0.30  (EMA temporal smoothing)")
    out.append("  Athlete          : " + athlete)
    out.append("  Note             : Simulated session (no camera required)")

    # ── Section 2 ──────────────────────────────────────────────────────────────
    out.append(section("SECTION 2 -- ACPF BASE WEIGHT PROFILE"))
    out.append("  These base weights define metric contribution BEFORE dynamic adjustment.")
    out.append("")
    out.append("  {:<30} {:>12}  Bar (max=0.30)".format("Metric", "Base Weight"))
    out.append("  " + "-"*68)
    base_w = acpf.BASE_WEIGHTS[ExerciseType.STRENGTH]
    for metric, wv in base_w.items():
        bar = bar_chart(wv*100, max_val=30, width=28)
        out.append("  {:<30} {:>10.3f}   {}".format(metric, wv, bar))
    out.append("")
    out.append("  ACPF shifts these weights at each rep based on threshold rules.")

    # ── Section 3: Physical Inputs ─────────────────────────────────────────────
    out.append(section("SECTION 3a -- PHYSICAL INPUTS PER REP"))
    out.append("")
    out.append("  {:>4}  {:>7}  {:>7}  {:>7}  {:>9}".format(
        "Rep", "Angle", "Form%", "ROM%", "Smooth%"))
    out.append("  " + "-"*48)
    for r in results:
        out.append("  {:>4}  {:>6.1f}d  {:>6.1f}%  {:>6.1f}%  {:>8.1f}%".format(
            r["rep_num"], r["angle"], r["form_score"],
            r["range_of_motion"], r["smoothness"]))

    # ── Section 3: Cognitive Inputs ────────────────────────────────────────────
    out.append(section("SECTION 3b -- COGNITIVE INPUTS PER REP"))
    out.append("")
    out.append("  {:>4}  {:>7}  {:>9}  {:>8}  {:>7}  {:<10}  {:>7}".format(
        "Rep", "Focus%", "Fatigue%", "Stress%", "Breath", "Emotion", "Motiv%"))
    out.append("  " + "-"*68)
    for r in results:
        out.append(
            "  {:>4}  {:>6.1f}%  {:>8.1f}%  {:>7.1f}%  {:>6.1f}   {:<10}  {:>6.1f}%".format(
                r["rep_num"], r["focus_score"], r["fatigue_level"],
                r["stress_index"], r["breathing_rate"],
                r["emotion"], r["motivation"]))

    # ── Section 3: ACPF Fusion Output ─────────────────────────────────────────
    out.append(section("SECTION 3c -- ACPF FUSION OUTPUT PER REP"))
    out.append("")
    out.append("  {:>4}  {:>7}  {:>7}  {:>7}  {:>7}  {:<9}  {}".format(
        "Rep", "Phys%", "Cogn%", "Well%", "ACPF%", "Risk", "Recommendation"))
    out.append("  " + "-"*78)
    for r in results:
        f = r["_fused"]
        action = f.recommended_action[:38]
        out.append(
            "  {:>4}  {:>6.1f}%  {:>6.1f}%  {:>6.1f}%  {:>6.1f}%  {:<9}  {}".format(
                r["rep_num"],
                f.physical_component,
                f.cognitive_component,
                f.overall_wellness,
                f.acpf_score,
                risk_label(f.risk_level.value),
                action))

    # ── Section 3: Adjustments ────────────────────────────────────────────────
    out.append(section("SECTION 3d -- DYNAMIC WEIGHT ADJUSTMENT LOG"))
    out.append("  Lists every ACPF rule that fired at each rep.")
    out.append("")
    any_adj = False
    for r in results:
        if r["_adjustments"]:
            any_adj = True
            out.append("  Rep {:>2}:".format(r["rep_num"]))
            for a in r["_adjustments"]:
                out.append("          * " + a)
    if not any_adj:
        out.append("  No threshold crossings fired -- base weights held throughout.")

    # ── Section 4: ASCII Charts ────────────────────────────────────────────────
    out.append(section("SECTION 4 -- ASCII BAR CHARTS (per rep)"))
    out.append("")

    series_list = [
        ("ACPF Composite Score (%)",  [r["_fused"].acpf_score        for r in results]),
        ("Overall Wellness    (%)",   [r["_fused"].overall_wellness   for r in results]),
        ("Physical Component  (%)",   [r["_fused"].physical_component for r in results]),
        ("Cognitive Component (%)",   [r["_fused"].cognitive_component for r in results]),
        ("Form Score          (%)",   [r["form_score"]                for r in results]),
        ("Focus Score         (%)",   [r["focus_score"]               for r in results]),
        ("Fatigue Level       (%)",   [r["fatigue_level"]             for r in results]),
        ("Stress Index        (%)",   [r["stress_index"]              for r in results]),
    ]

    for name, vals in series_list:
        avg = float(np.mean(vals))
        mn  = float(np.min(vals))
        mx  = float(np.max(vals))
        out.append("  " + name + "   Avg:{:.1f}  Min:{:.1f}  Max:{:.1f}".format(avg, mn, mx))
        out.append("  " + "Rep  " + "Value  " + "Bar (0-100)")
        out.append("  " + "-"*55)
        for r, v in zip(results, vals):
            bar = bar_chart(v, width=35)
            out.append("  {:>3}   {:>5.1f}%  {}".format(r["rep_num"], v, bar))
        spark = sparkline(vals, width=n_reps*2, lo=0, hi=100)
        out.append("  Trend: [" + spark + "]")
        out.append("")

    # ── Section 4b: Weight Evolution ──────────────────────────────────────────
    out.append(section("SECTION 4b -- ATTENTION WEIGHT EVOLUTION ACROSS KEY REPS"))
    out.append("")
    out.append("  Shows how ACPF dynamically shifted metric weights.")
    out.append("")
    key_indices = [0, 4, 9, 14, min(19, len(results)-1)]
    key_indices = sorted(set(key_indices))
    metric_keys = list(results[0]["_weights"].keys())

    header_row = "  {:<28}".format("Metric")
    for ki in key_indices:
        header_row += "  Rep{:>2}".format(results[ki]["rep_num"])
    out.append(header_row)
    out.append("  " + "-" * (28 + len(key_indices)*8))
    for mk in metric_keys:
        row = "  {:<28}".format(mk)
        for ki in key_indices:
            w = results[ki]["_weights"].get(mk, 0.0)
            row += "  {:>5.3f}".format(w)
        out.append(row)
    out.append("")
    out.append("  Changes from Rep 1 values = ACPF threshold rules firing.")

    # ── Section 5: Summary ────────────────────────────────────────────────────
    out.append(section("SECTION 5 -- SESSION SUMMARY STATISTICS"))
    out.append("")
    out.append("  {:<35}  {:>8}  {:>14}  Bar (0-100)".format("Metric", "Value", "Grade"))
    out.append("  " + "-"*76)

    stat_rows = [
        ("ACPF Composite Score",     summary.get("avg_acpf",       0.0), True),
        ("Overall Wellness",          summary.get("avg_wellness",    0.0), True),
        ("Average Form Quality",      summary.get("avg_form",        0.0), True),
        ("Average Focus Score",       summary.get("avg_focus",       0.0), True),
        ("Average Fatigue Level",     summary.get("avg_fatigue",     0.0), False),
        ("Average Stress Index",      summary.get("avg_stress",      0.0), False),
        ("Average Motivation",        summary.get("avg_motivation",  0.0), True),
        ("Peak Wellness",             summary.get("peak_wellness",   0.0), True),
        ("Lowest Wellness",           summary.get("lowest_wellness", 0.0), True),
        ("Peak Form",                 summary.get("peak_form",       0.0), True),
    ]

    for label, val, higher_good in stat_rows:
        val = float(val)
        g   = grade(val if higher_good else 100 - val)
        suffix = " (lower=better)" if not higher_good else ""
        bar = bar_chart(val, width=25)
        out.append("  {:<35}  {:>7.1f}%  {}  {}{}".format(
            label, val, g, bar, suffix))

    out.append("")
    adj_count  = summary.get("adjustment_count", 0)
    total_reps = summary.get("total_reps", n_reps)
    duration   = summary.get("duration_formatted", "N/A")
    out.append("  Adaptive Weight Adjustments Made : {}".format(adj_count))
    out.append("  Adjustment Frequency             : {:.1f}% of reps".format(
        adj_count/max(total_reps,1)*100))
    out.append("  Total Reps Recorded              : {}".format(total_reps))
    out.append("  Session Duration                 : {}".format(duration))

    # Risk distribution
    out.append("")
    out.append("  Risk Level Distribution:")
    risk_counts = {}
    for r in results:
        rv = r["_fused"].risk_level.value
        risk_counts[rv] = risk_counts.get(rv, 0) + 1
    for rv in ["SAFE", "CAUTION", "STOP"]:
        cnt = risk_counts.get(rv, 0)
        pct = cnt / len(results) * 100
        bar = bar_chart(pct, max_val=100, width=25)
        icon = {"SAFE":"[OK] ","CAUTION":"[!!] ","STOP":"[XX] "}.get(rv,"     ")
        out.append("    {}  {:<8} : {:>3} reps  ({:>5.1f}%)  {}".format(
            icon, rv, cnt, pct, bar))

    # ── Section 6: Algorithm Explanation ──────────────────────────────────────
    out.append(section("SECTION 6 -- ACPF ALGORITHM EXPLANATION"))
    out.append("""
  ADAPTIVE COGNITIVE-PHYSICAL FUSION (ACPF)
  ==========================================

  The ACPF algorithm is the core original contribution of this project.
  It combines physical and cognitive biometric signals into a unified
  Wellness Score using DYNAMICALLY ADAPTIVE attention weights.

  Unlike traditional static weighted-average systems, ACPF re-weights
  every frame/rep based on live threshold-crossing rules, automatically
  shifting priority toward the most safety-critical signal.

  PIPELINE:
  ---------
  Step 1  INPUTS
          Physical : form_score, range_of_motion, movement_smoothness
          Cognitive: focus_score, fatigue_level, stress_index,
                     breathing_rate, emotion, motivation

  Step 2  BASE WEIGHTS (exercise-type specific)
          Strength:  form=0.25, ROM=0.20, smooth=0.15,
                     focus=0.15, fatigue=0.15, stress=0.05, breathing=0.05

  Step 3  DYNAMIC WEIGHT ADJUSTMENT  <-- KEY INNOVATION
          Rule 1: fatigue  > 70%  --> boost fatigue weight  (+20% scaled)
          Rule 2: stress   > 65%  --> boost stress + focus  (+15% scaled)
          Rule 3: form     < 55%  --> boost form weight     (+20% scaled)
          Rule 4: focus    < 45%  --> boost focus weight    (+15% scaled)
          Rule 5: breathing out of range --> boost br weight (+10%)
          All weights re-normalised to sum = 1.0 after each adjustment.

  Step 4  COMPONENT SCORES
          physical_score  = SUM( physical_metric * its_weight )
          cognitive_score = SUM( cognitive_metric * its_weight )

  Step 5  FUSION
          raw_wellness = physical_score * w_phys + cognitive_score * w_cog

  Step 6  TEMPORAL SMOOTHING (Exponential Moving Average)
          wellness = 0.30 * raw_wellness + 0.70 * prev_wellness

  Step 7  ACPF COMPOSITE SCORE
          acpf_score = wellness*0.50 + motivation*0.30 + form*0.20

  Step 8  RISK ASSESSMENT
          fatigue > 85%  --> STOP immediately
          stress  > 80%  --> STOP immediately
          wellness >= 70  --> SAFE
          wellness 50-70  --> CAUTION
          wellness < 50   --> STOP

  WHY THIS IS NOVEL:
  ------------------
  Traditional systems apply the SAME formula to every athlete at every
  moment. ACPF produces a personalised, context-aware wellness score
  by dynamically re-balancing weights in real time.

  When an athlete is highly fatigued, ACPF automatically elevates the
  importance of fatigue monitoring over form scoring -- mirroring how
  an experienced coach shifts attention based on what they observe.

  This results in a system that responds intelligently to each
  athlete's unique real-time state rather than applying a rigid formula.
  """)

    # ── Footer ─────────────────────────────────────────────────────────────────
    out.append(dline())
    out.append("  END OF REPORT".center(W))
    out.append(("  Session ID : " + str(summary.get("session_id","N/A"))).center(W))
    out.append(("  Date       : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")).center(W))
    out.append(dline())

    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    EXERCISE = "Bicep Curl"
    EX_TYPE  = ExerciseType.STRENGTH
    N_REPS   = 20
    ATHLETE  = "Demo Athlete"

    print("\n" + dline())
    print("  MODULE 3 -- ACPF Algorithm  |  FitPulse Pro".center(W))
    print("  Simulating {}-rep {} session...".format(N_REPS, EXERCISE).center(W))
    print(dline())

    # Init ACPF
    acpf = ACPFAlgorithm(
        exercise_type    = EX_TYPE,
        smoothing_factor = 0.30,
        athlete_name     = ATHLETE,
        exercise_name    = EXERCISE
    )

    # Simulate reps
    sim_reps = simulate_session(n_reps=N_REPS, seed=42)

    # Run ACPF fusion on each rep
    results = []
    for rep_data in sim_reps:
        phys = PhysicalState(
            form_score           = rep_data["form_score"],
            range_of_motion      = rep_data["range_of_motion"],
            movement_smoothness  = rep_data["smoothness"],
            rep_count            = rep_data["rep_num"],
            angle                = rep_data["angle"]
        )
        cog = CognitiveState(
            focus_score    = rep_data["focus_score"],
            stress_index   = rep_data["stress_index"],
            fatigue_level  = rep_data["fatigue_level"],
            breathing_rate = rep_data["breathing_rate"],
            emotion        = rep_data["emotion"],
            emotion_score  = 70.0,
            motivation     = rep_data["motivation"]
        )
        fused = acpf.fuse(phys, cog)
        rep_data["_fused"]       = fused
        rep_data["_adjustments"] = list(fused.adjustments_made)
        rep_data["_weights"]     = dict(fused.attention_weights)
        results.append(rep_data)
        time.sleep(0.01)

    summary = acpf.get_session_summary()

    # Build and print report
    report = build_report(results, summary, acpf,
                          EXERCISE, EX_TYPE.value.title(), N_REPS, ATHLETE)
    print(report)

    # Save text report
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join("output", "mod3_acpf_report_{}.txt".format(ts))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n  Saved text report   --> {}".format(txt_path))

    # Save HTML dashboard
    try:
        html      = acpf.generate_dashboard()
        html_path = os.path.join("output", "acpf_dashboard_{}.html".format(ts))
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print("  Saved HTML dashboard --> {}".format(html_path))
        print("  Open the HTML file in any browser for interactive charts.\n")
    except Exception as e:
        print("  HTML dashboard generation failed: {}\n".format(e))


if __name__ == "__main__":
    main()