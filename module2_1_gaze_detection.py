"""
╔══════════════════════════════════════════════════════════════════════════════╗
║       MODULE 2.1 — COGNITIVE SIGNAL EXTRACTION : GAZE DETECTION            ║
║       FitPulse Pro  |  Cognitive-Physical Fitness System                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

DESCRIPTION:
    Runs the project's GazeEngine on live webcam video.

    Detects per-frame:
      • Face position (Haar cascade)
      • Left / Right eye state  (OPEN / CLOSED)
      • Iris centre direction   (centre / left / right)
      • Focus Score  0–100
      • Drowsiness detection
      • Session-level alertness statistics

    Visual output includes:
      • Face bounding box + eye ROI highlights
      • Real-time focus score gauge (colour bar)
      • Rolling focus-score waveform (last 120 frames)
      • Drowsiness warning overlay
      • Full session statistics panel

PRESS:
    Q  — quit
    S  — save screenshot to output/
    R  — reset session statistics

RUN:
    python module2_1_gaze_detection.py
"""

import cv2
import numpy as np
import time
import os
import sys
from datetime import datetime
from collections import deque

# ── Ensure cognitive/ folder is importable ────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cognitive"))

from cognitive.gaze_engine import GazeEngine

# ── Constants ──────────────────────────────────────────────────────────────────
WIN_TITLE   = "MODULE 2.1 — Gaze Detection  |  FitPulse Pro"
FONT        = cv2.FONT_HERSHEY_DUPLEX
FONT_S      = cv2.FONT_HERSHEY_SIMPLEX
WAVEFORM_N  = 120    # number of historical focus scores to plot
CHART_H     = 130    # height of waveform chart

CYAN   = (220, 200, 0)
GREEN  = (0,   220, 100)
YELLOW = (0,   200, 255)
RED    = (60,  60,  230)
WHITE  = (255, 255, 255)
DARK   = (10,  10,  25)
TEAL   = (220, 180, 0)
ORANGE = (30,  140, 255)
PURPLE = (200, 80,  180)

os.makedirs("output", exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def put_bg(img, text, pos, scale=0.52, color=WHITE, thickness=1, bg=DARK, pad=5):
    f = FONT_S
    (tw, th), _ = cv2.getTextSize(text, f, scale, thickness)
    x, y = pos
    cv2.rectangle(img, (x-pad, y-th-pad), (x+tw+pad, y+pad), bg, -1)
    cv2.putText(img, text, (x, y), f, scale, color, thickness, cv2.LINE_AA)


def score_color(score):
    """Return BGR colour that transitions red → yellow → green with score."""
    if score >= 70:
        t = (score - 70) / 30
        return (int(0 + t*0), int(150 + t*70), int(50 + t*50))
    elif score >= 40:
        t = (score - 40) / 30
        return (0, int(120 + t*30), int(200 - t*150))
    else:
        return (40, 40, 200)


def draw_focus_gauge(img, score, x, y, w=220, h=28):
    """Horizontal focus-score gauge with colour gradient fill."""
    cv2.rectangle(img, (x, y), (x+w, y+h), (40,40,40), -1)
    fill = int(w * score / 100)
    col  = score_color(score)
    cv2.rectangle(img, (x, y), (x+fill, y+h), col, -1)
    cv2.rectangle(img, (x, y), (x+w, y+h), (100,100,100), 1)
    put_bg(img, f"FOCUS  {score:.1f} / 100", (x+4, y+h-5),
           scale=0.48, color=WHITE, bg=(0,0,0,0), pad=0)


def draw_waveform(history, chart_w, chart_h):
    """Plot rolling focus score waveform on a dark canvas."""
    chart = np.zeros((chart_h, chart_w, 3), dtype=np.uint8)
    chart[:] = (12, 12, 28)

    # Grid lines at 0, 25, 50, 75, 100
    for pct in [0, 25, 50, 75, 100]:
        gy = int(chart_h - pct / 100 * (chart_h - 20) - 10)
        cv2.line(chart, (0, gy), (chart_w, gy), (35,35,55), 1)
        cv2.putText(chart, str(pct), (2, gy - 2), FONT_S, 0.32, (80,80,100), 1)

    # Waveform polyline
    pts = []
    data = list(history)
    n    = len(data)
    if n >= 2:
        for i, v in enumerate(data):
            px = int(i / max(n-1, 1) * (chart_w - 1))
            py = int(chart_h - v / 100 * (chart_h - 20) - 10)
            pts.append([px, py])
        pts_arr = np.array(pts, dtype=np.int32)
        cv2.polylines(chart, [pts_arr], False, (0, 200, 255), 2, cv2.LINE_AA)

        # Shade under curve
        fill_pts = pts + [[chart_w-1, chart_h-1], [0, chart_h-1]]
        cv2.fillPoly(chart, [np.array(fill_pts, dtype=np.int32)],
                     (0, 80, 120))

    # Title
    cv2.putText(chart, "FOCUS SCORE WAVEFORM (last 120 frames)",
                (8, 14), FONT_S, 0.40, (0, 200, 255), 1, cv2.LINE_AA)
    return chart


def draw_eye_state_boxes(img, left_state, right_state):
    """Draw two eye-state indicator boxes (L / R)."""
    x0, y0 = 10, 65
    for i, (state, label) in enumerate([(left_state, "L.EYE"), (right_state, "R.EYE")]):
        bx = x0 + i * 115
        col = GREEN if state == "OPEN" else RED
        cv2.rectangle(img, (bx, y0), (bx+105, y0+46), (20,20,40), -1)
        cv2.rectangle(img, (bx, y0), (bx+105, y0+46), col, 2)
        cv2.putText(img, label, (bx+6, y0+16), FONT_S, 0.45, col, 1, cv2.LINE_AA)
        cv2.putText(img, state,  (bx+6, y0+38), FONT,   0.55, WHITE, 1, cv2.LINE_AA)


def draw_drowsy_warning(img, is_drowsy, drowsy_pct, w, h):
    if not is_drowsy:
        return
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 180), -1)
    cv2.addWeighted(overlay, 0.22, img, 0.78, 0, img)
    put_bg(img, f"⚠ DROWSINESS DETECTED  ({drowsy_pct:.0f}%)",
           (w//2 - 220, h//2 + 20), scale=0.9, color=(0,0,255),
           bg=(0,0,0), pad=10)


def draw_stats_panel(img, result, session_start, frame_num, fps, w, h):
    """Right-side statistics panel."""
    px, py = w - 285, 60
    panel_h = 310
    overlay = img.copy()
    cv2.rectangle(overlay, (px-10, py-10), (w-4, py+panel_h), (8,8,22), -1)
    cv2.addWeighted(overlay, 0.82, img, 0.18, 0, img)
    cv2.rectangle(img, (px-10, py-10), (w-4, py+panel_h), (60,60,100), 1)

    elapsed  = time.time() - session_start
    title    = "COGNITIVE SIGNAL — GAZE"
    cv2.putText(img, title, (px, py+8), FONT_S, 0.46, (0,220,255), 1, cv2.LINE_AA)
    cv2.line(img, (px-8, py+14), (w-6, py+14), (60,60,100), 1)

    rows = [
        ("Focus Score",    f"{result.get('focus_score',0):.1f} / 100",   YELLOW),
        ("Left Eye",       result.get('left_eye',  '—'),                  GREEN if result.get('left_eye')=='OPEN'  else RED),
        ("Right Eye",      result.get('right_eye', '—'),                  GREEN if result.get('right_eye')=='OPEN' else RED),
        ("Drowsy",         "YES ⚠️" if result.get('is_drowsy') else "No",  RED if result.get('is_drowsy') else GREEN),
        ("Drowsy %",       f"{result.get('drowsy_pct',0):.1f}%",          ORANGE),
        ("Eyes Open %",    f"{result.get('eyes_open_pct',0):.1f}%",       GREEN),
        ("Alert Events",   str(result.get('alert_count', 0)),             PURPLE),
        ("Face Detected",  "YES" if result.get('face_detected') else "NO", GREEN if result.get('face_detected') else RED),
        ("Method",         result.get('method','opencv').upper(),         (180,180,180)),
        ("Frame #",        str(frame_num),                                 (130,130,130)),
        ("Elapsed",        f"{elapsed:.1f}s",                              (130,130,130)),
        ("FPS",            f"{fps:.1f}",                                   CYAN),
    ]

    for i, (label, val, col) in enumerate(rows):
        ry = py + 32 + i * 22
        cv2.putText(img, f"{label}:", (px, ry),  FONT_S, 0.40, (140,140,160), 1)
        cv2.putText(img, val,  (px+140, ry), FONT_S, 0.42, col, 1, cv2.LINE_AA)


def draw_face_box(img, lm_result, gray, face_cascade, eye_cascade):
    """Draw face + eye ROI boxes directly on the frame."""
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60,60))
    for (x, y, fw, fh) in faces:
        cv2.rectangle(img, (x,y), (x+fw, y+fh), (0,220,100), 2)
        put_bg(img, "FACE", (x+4, y-4), scale=0.45, color=GREEN, bg=(0,0,0,0), pad=2)
        upper = gray[y: y+fh//2, x: x+fw]
        eyes  = eye_cascade.detectMultiScale(upper, 1.1, 6, minSize=(14,14))
        for (ex, ey, ew, eh) in eyes[:2]:
            cv2.rectangle(img, (x+ex, y+ey), (x+ex+ew, y+ey+eh), YELLOW, 2)


def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Load gaze engine (uses the project's full engine)
    gaze_engine = GazeEngine()

    # Haar cascades (for drawing boxes)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade  = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

    focus_history = deque(maxlen=WAVEFORM_N)
    session_start = time.time()
    frame_num     = 0
    fps           = 0
    fps_timer     = time.time()
    fps_counter   = 0
    last_result   = {"focus_score": 50, "left_eye": "DETECTING",
                     "right_eye": "DETECTING", "is_drowsy": False,
                     "drowsy_pct": 0, "eyes_open_pct": 100,
                     "alert_count": 0, "face_detected": False, "method": "opencv"}

    print("\n" + "="*70)
    print("  MODULE 2.1 — Cognitive Signal Extraction: GAZE DETECTION")
    print("  FitPulse Pro  |  Cognitive-Physical Fitness System")
    print("="*70)
    print("  Controls:  Q=Quit   S=Screenshot   R=Reset stats")
    print("="*70 + "\n")

    while True:
        ret, raw = cap.read()
        if not ret:
            break

        frame_num   += 1
        fps_counter += 1
        elapsed      = time.time() - session_start

        if time.time() - fps_timer >= 1.0:
            fps         = fps_counter
            fps_counter = 0
            fps_timer   = time.time()

        # Flip for self-view
        frame = cv2.flip(raw, 1)
        h, w  = frame.shape[:2]

        # ── Run gaze engine ────────────────────────────────────────────────────
        result      = gaze_engine.predict_from_frame(frame)
        last_result = result
        focus_history.append(result.get('focus_score', 50))

        # ── Face & eye boxes ───────────────────────────────────────────────────
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        draw_face_box(frame, result, gray, face_cascade, eye_cascade)

        # ── Drowsy warning ─────────────────────────────────────────────────────
        draw_drowsy_warning(frame, result.get('is_drowsy'), result.get('drowsy_pct', 0), w, h)

        # ── Eye state boxes ────────────────────────────────────────────────────
        draw_eye_state_boxes(frame, result.get('left_eye','—'), result.get('right_eye','—'))

        # ── Focus gauge (under eye boxes) ─────────────────────────────────────
        draw_focus_gauge(frame, result.get('focus_score', 50), 10, 125)

        # ── Stats panel ────────────────────────────────────────────────────────
        draw_stats_panel(frame, result, session_start, frame_num, fps, w, h)

        # ── Top bar ────────────────────────────────────────────────────────────
        cv2.rectangle(frame, (0,0), (w, 52), DARK, -1)
        cv2.putText(frame, "MODULE 2.1 — COGNITIVE SIGNAL EXTRACTION: GAZE DETECTION",
                    (10, 22), FONT_S, 0.56, (0,220,255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"FitPulse Pro  |  FPS:{fps}  |  Frame:{frame_num}  |  Elapsed:{elapsed:.1f}s",
                    (10, 44), FONT_S, 0.40, (150,180,200), 1, cv2.LINE_AA)

        # ── Waveform chart (strip below camera view) ───────────────────────────
        wave = draw_waveform(focus_history, w, CHART_H)

        # ── Label for waveform ─────────────────────────────────────────────────
        lbl_bar = np.zeros((20, w, 3), dtype=np.uint8)
        lbl_bar[:] = (8, 8, 22)
        cv2.putText(lbl_bar, "FOCUS SCORE HISTORY  (blue=actual, threshold lines: 25 / 50 / 75)",
                    (8, 14), FONT_S, 0.38, (0,200,255), 1, cv2.LINE_AA)

        display = np.vstack([frame, lbl_bar, wave])
        cv2.imshow(WIN_TITLE, display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"output/mod2_1_gaze_{ts}.png"
            cv2.imwrite(path, display)
            print(f"[MOD2.1] Screenshot saved → {path}")
        elif key == ord('r'):
            gaze_engine.reset()
            focus_history.clear()
            session_start = time.time()
            frame_num     = 0
            print("[MOD2.1] Stats reset")

    cap.release()
    cv2.destroyAllWindows()

    stats = gaze_engine.get_session_stats()
    print(f"\n[MOD2.1] Session complete:")
    print(f"  Total frames    : {stats['total_frames']}")
    print(f"  Drowsy frames   : {stats['drowsy_frames']}")
    print(f"  Alert events    : {stats['alert_count']}")
    print(f"  Drowsy % (sess) : {stats['drowsy_pct_session']}%")


if __name__ == "__main__":
    main()
