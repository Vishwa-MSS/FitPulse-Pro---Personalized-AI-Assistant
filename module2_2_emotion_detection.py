"""
╔══════════════════════════════════════════════════════════════════════════════╗
║       MODULE 2.2 — COGNITIVE SIGNAL EXTRACTION : EMOTION DETECTION         ║
║       FitPulse Pro  |  Cognitive-Physical Fitness System                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

DESCRIPTION:
    Runs the project's EmotionEngine on live webcam video.
    Detects 7 facial expressions in real time and maps each to a
    fitness coaching insight.

    Emotions detected:
        Happy · Sad · Angry · Fear · Disgust · Surprise · Neutral

    Visual output includes:
      • Live face bounding box with emotion label
      • Confidence bar for current emotion
      • All-7 emotion probability bar chart
      • Fitness coaching message
      • Rolling emotion label history strip
      • Session-level emotion frequency table

PRESS:
    Q  — quit
    S  — save screenshot to output/
    R  — reset session

RUN:
    python module2_2_emotion_detection.py
"""

import cv2
import numpy as np
import time
import os
import sys
from datetime import datetime
from collections import deque, Counter

# ── Imports ────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cognitive"))

from cognitive.emotion_engine import EmotionEngine, EMOTION_LABELS, EMOTION_FITNESS_MAP

# ── Constants ──────────────────────────────────────────────────────────────────
WIN_TITLE  = "MODULE 2.2 — Emotion Detection  |  FitPulse Pro"
FONT       = cv2.FONT_HERSHEY_DUPLEX
FONT_S     = cv2.FONT_HERSHEY_SIMPLEX

DARK  = (10,  10,  25)
WHITE = (255, 255, 255)
CYAN  = (220, 200, 0)
GREEN = (0,   210, 100)

EMOTION_COLORS_BGR = {
    'Angry':    (60,   60,  220),
    'Disgust':  (30,  140,  255),
    'Fear':     (30,  180,  255),
    'Happy':    (0,   200,  100),
    'Sad':      (220,  80,   80),
    'Surprise': (200,  80,  200),
    'Neutral':  (220, 180,    0),
}

HISTORY_LEN  = 150   # frames of emotion label history
BAR_CHART_H  = 200   # height of 7-emotion probability chart

os.makedirs("output", exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def put_bg(img, text, pos, scale=0.52, color=WHITE, thickness=1, pad=5, bg=DARK):
    (tw, th), _ = cv2.getTextSize(text, FONT_S, scale, thickness)
    x, y = pos
    cv2.rectangle(img, (x-pad, y-th-pad), (x+tw+pad, y+pad), bg, -1)
    cv2.putText(img, text, (x, y), FONT_S, scale, color, thickness, cv2.LINE_AA)


def draw_emotion_prob_bars(probs, chart_w, chart_h):
    """
    Horizontal bar chart of all 7 emotion probabilities.
    Returns a BGR image of size (chart_h, chart_w, 3).
    """
    chart = np.zeros((chart_h, chart_w, 3), dtype=np.uint8)
    chart[:] = (12, 12, 28)

    n     = len(EMOTION_LABELS)
    row_h = (chart_h - 30) // n
    max_w = chart_w - 160

    cv2.putText(chart, "EMOTION PROBABILITY DISTRIBUTION",
                (8, 16), FONT_S, 0.44, (0, 220, 255), 1, cv2.LINE_AA)

    for i, emo in enumerate(EMOTION_LABELS):
        pct   = probs.get(emo, 0.0)
        col   = EMOTION_COLORS_BGR.get(emo, WHITE)
        y0    = 28 + i * row_h
        bar_w = int(max_w * pct / 100)

        # Background track
        cv2.rectangle(chart, (150, y0+3), (150+max_w, y0+row_h-6), (35,35,50), -1)
        # Fill
        cv2.rectangle(chart, (150, y0+3), (150+bar_w, y0+row_h-6), col, -1)
        # Label
        cv2.putText(chart, f"{emo:<9s}", (4,  y0+row_h-8), FONT_S, 0.42, col, 1, cv2.LINE_AA)
        cv2.putText(chart, f"{pct:5.1f}%", (150+max_w+6, y0+row_h-8),
                    FONT_S, 0.40, WHITE, 1, cv2.LINE_AA)

    return chart


def draw_history_strip(history, strip_w):
    """
    Draw a coloured strip of the last HISTORY_LEN emotion labels.
    Each frame is 1px wide; colour-coded by emotion.
    """
    strip_h = 36
    strip   = np.zeros((strip_h, strip_w, 3), dtype=np.uint8)
    strip[:] = (15, 15, 28)

    data = list(history)[-strip_w:]   # at most strip_w entries
    for i, emo in enumerate(data):
        col = EMOTION_COLORS_BGR.get(emo, (60,60,60))
        strip[4:strip_h-10, i:i+1] = col

    cv2.putText(strip, "EMOTION HISTORY STRIP (L=oldest → R=current)",
                (4, strip_h-4), FONT_S, 0.35, (180,180,180), 1, cv2.LINE_AA)
    return strip


def draw_session_table(img, emotion_counts, total_frames, x, y, w, h):
    """Draw session emotion frequency table as overlay."""
    panel_h = len(EMOTION_LABELS) * 22 + 55
    overlay = img.copy()
    cv2.rectangle(overlay, (x-8, y-8), (x+w+8, y+panel_h), (8,8,22), -1)
    cv2.addWeighted(overlay, 0.82, img, 0.18, 0, img)
    cv2.rectangle(img, (x-8, y-8), (x+w+8, y+panel_h), (60,60,100), 1)

    cv2.putText(img, "SESSION FREQUENCY", (x, y+10), FONT_S, 0.44, (0,220,255), 1, cv2.LINE_AA)
    cv2.putText(img, f"{'Emotion':<12} {'Frames':>7} {'%':>6}",
                (x, y+30), FONT_S, 0.36, (120,120,140), 1, cv2.LINE_AA)
    cv2.line(img, (x, y+34), (x+w, y+34), (50,50,70), 1)

    for i, emo in enumerate(EMOTION_LABELS):
        cnt  = emotion_counts.get(emo, 0)
        pct  = cnt / max(total_frames, 1) * 100
        col  = EMOTION_COLORS_BGR.get(emo, WHITE)
        row  = y + 52 + i * 22
        cv2.putText(img, f"{emo:<10}", (x, row),     FONT_S, 0.38, col,   1, cv2.LINE_AA)
        cv2.putText(img, f"{cnt:>6}", (x+110, row),  FONT_S, 0.38, WHITE, 1, cv2.LINE_AA)
        cv2.putText(img, f"{pct:>5.1f}%", (x+155, row), FONT_S, 0.36, (180,180,180), 1, cv2.LINE_AA)


def draw_current_emotion(img, emotion, conf, fitness_info, x, y):
    """Big emotion display box."""
    col   = EMOTION_COLORS_BGR.get(emotion, WHITE)
    bw, bh = 280, 120
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x+bw, y+bh), (15,15,35), -1)
    cv2.addWeighted(overlay, 0.85, img, 0.15, 0, img)
    cv2.rectangle(img, (x, y), (x+bw, y+bh), col, 3)

    cv2.putText(img, "CURRENT EMOTION", (x+6, y+16), FONT_S, 0.40, (150,150,170), 1)
    cv2.putText(img, emotion,   (x+6, y+55), FONT, 1.0, col,   2, cv2.LINE_AA)
    cv2.putText(img, f"Conf: {conf:.1f}%", (x+6, y+76), FONT_S, 0.45, WHITE, 1)

    # Confidence bar
    cbar_w = int((bw - 12) * conf / 100)
    cv2.rectangle(img, (x+6, y+84), (x+bw-6, y+100), (40,40,40), -1)
    cv2.rectangle(img, (x+6, y+84), (x+6+cbar_w, y+100), col, -1)

    # Fitness status label (below box)
    put_bg(img, fitness_info.get('status','—'), (x, y+bh+8),
           scale=0.46, color=col, pad=5)


def draw_face_box(img, gray, face_cascade, emotion, col):
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(45,45))
    for (x, y, fw, fh) in faces:
        cv2.rectangle(img, (x,y), (x+fw, y+fh), col, 2)
        put_bg(img, emotion, (x, y-6), scale=0.58, color=col, bg=(0,0,0,0), pad=3)
    return faces


def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    engine       = EmotionEngine()
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    emotion_history = deque(maxlen=HISTORY_LEN)
    emotion_counts  = Counter()

    session_start = time.time()
    frame_num     = 0
    fps = 0
    fps_timer   = time.time()
    fps_counter = 0

    last_result = {
        'emotion': 'Neutral', 'confidence': 0.0,
        'fitness_status': '—', 'message': '—',
        'color': '#64748b', 'probabilities': {e:0.0 for e in EMOTION_LABELS},
        'face_detected': False,
    }

    print("\n" + "="*70)
    print("  MODULE 2.2 — Cognitive Signal Extraction: EMOTION DETECTION")
    print("  FitPulse Pro  |  Cognitive-Physical Fitness System")
    print("="*70)
    print("  Controls:  Q=Quit   S=Screenshot   R=Reset session")
    print("="*70 + "\n")

    while True:
        ret, raw = cap.read()
        if not ret:
            break

        frame_num   += 1
        fps_counter += 1

        if time.time() - fps_timer >= 1.0:
            fps         = fps_counter
            fps_counter = 0
            fps_timer   = time.time()

        frame = cv2.flip(raw, 1)
        h, w  = frame.shape[:2]

        # ── Emotion detection ──────────────────────────────────────────────────
        result = engine.predict_from_frame(frame)
        last_result = result

        emotion   = result.get('emotion', 'Neutral')
        conf      = result.get('confidence', 0.0)
        probs     = result.get('probabilities', {e:0.0 for e in EMOTION_LABELS})
        face_det  = result.get('face_detected', False)
        fit_info  = EMOTION_FITNESS_MAP.get(emotion, EMOTION_FITNESS_MAP['Neutral'])
        col       = EMOTION_COLORS_BGR.get(emotion, WHITE)

        emotion_history.append(emotion)
        if face_det:
            emotion_counts[emotion] += 1

        # ── Face box ───────────────────────────────────────────────────────────
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        draw_face_box(frame, gray, face_cascade, emotion, col)

        # ── Current emotion display ────────────────────────────────────────────
        draw_current_emotion(frame, emotion, conf, fit_info, 10, 65)

        # ── Fitness message ────────────────────────────────────────────────────
        msg = result.get('message', '')
        if msg:
            put_bg(frame, msg[:60], (10, 210), scale=0.44, color=(200,200,200), pad=5)

        # ── Session frequency table ────────────────────────────────────────────
        draw_session_table(frame, emotion_counts, frame_num,
                           x=w-280, y=65, w=268, h=h-100)

        # ── Method & face detection indicator ─────────────────────────────────
        method = result.get('method','geometric').upper()
        mcol   = (0,220,150) if result.get('face_detected') else (60,60,200)
        put_bg(frame, f"Method: {method}  |  Face: {'DETECTED' if face_det else 'NOT FOUND'}",
               (10, h-60), scale=0.44, color=mcol, pad=4)

        # ── Top bar ────────────────────────────────────────────────────────────
        cv2.rectangle(frame, (0,0), (w, 52), DARK, -1)
        cv2.putText(frame, "MODULE 2.2 — COGNITIVE SIGNAL EXTRACTION: EMOTION DETECTION",
                    (10, 22), FONT_S, 0.56, (0,220,255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"FPS: {fps}  |  Frame: {frame_num}  |  Elapsed: {time.time()-session_start:.1f}s  |  Q=Quit  S=Screenshot  R=Reset",
                    (10, 44), FONT_S, 0.38, (150,180,200), 1, cv2.LINE_AA)

        # ── Probability bar chart ──────────────────────────────────────────────
        prob_chart = draw_emotion_prob_bars(probs, w, BAR_CHART_H)

        # ── History strip ──────────────────────────────────────────────────────
        hist_strip = draw_history_strip(emotion_history, w)

        # ── Stack ─────────────────────────────────────────────────────────────
        display = np.vstack([frame, prob_chart, hist_strip])
        cv2.imshow(WIN_TITLE, display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"output/mod2_2_emotion_{ts}.png"
            cv2.imwrite(path, display)
            print(f"[MOD2.2] Screenshot saved → {path}")
        elif key == ord('r'):
            engine._geo._label_hist.clear()
            emotion_history.clear()
            emotion_counts.clear()
            frame_num = 0
            session_start = time.time()
            print("[MOD2.2] Session reset")

    cap.release()
    cv2.destroyAllWindows()

    if emotion_counts:
        print(f"\n[MOD2.2] Session emotion summary:")
        total = sum(emotion_counts.values())
        for emo, cnt in emotion_counts.most_common():
            print(f"  {emo:<12} : {cnt:4d} frames  ({cnt/total*100:5.1f}%)")


if __name__ == "__main__":
    main()
