"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          MODULE 1 — VIDEO ACQUISITION & PREPROCESSING                      ║
║          FitPulse Pro  |  Cognitive-Physical Fitness System                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

DESCRIPTION:
    Captures live webcam video, applies MediaPipe Pose to extract 33 body
    landmarks, computes real-time joint angles, detects exercise movement
    stages (UP / DOWN), counts repetitions, and shows a live annotated
    display suitable for documentation screenshots.

PRESS:
    Q  — quit
    S  — save a screenshot to output/

RUN:
    python module1_video_acquisition.py
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import time
import os
from datetime import datetime

# ── MediaPipe setup ────────────────────────────────────────────────────────────
mp_pose    = mp.solutions.pose
mp_draw    = mp.solutions.drawing_utils
mp_style   = mp.solutions.drawing_styles

# ── Constants ──────────────────────────────────────────────────────────────────
WIN_TITLE   = "MODULE 1 — Video Acquisition & Preprocessing  |  FitPulse Pro"
DEMO_EXER   = "Bicep Curl"          # default exercise for angle computation
FONT        = cv2.FONT_HERSHEY_DUPLEX
FONT_SMALL  = cv2.FONT_HERSHEY_SIMPLEX
GREEN       = (0,   220, 100)
CYAN        = (0,   220, 255)
YELLOW      = (30,  210, 255)
WHITE       = (255, 255, 255)
RED         = (60,  60,  220)
ORANGE      = (30,  140, 255)
DARK        = (20,  20,  20)
TEAL        = (180, 220, 0)

os.makedirs("output", exist_ok=True)

# ── Utility ────────────────────────────────────────────────────────────────────
def angle_3pts(a, b, c):
    """Angle (degrees) at point b given three (x,y) points."""
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba, bc  = a - b, c - b
    cosA    = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return math.degrees(math.acos(np.clip(cosA, -1, 1)))

def lm_xy(landmarks, idx, w, h):
    l = landmarks[idx]
    return int(l.x * w), int(l.y * h)

def put_text_bg(img, text, pos, font=FONT_SMALL, scale=0.55, color=WHITE,
                thickness=1, bg=DARK, pad=6):
    """Draw text with dark background for readability."""
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x, y = pos
    cv2.rectangle(img, (x-pad, y-th-pad), (x+tw+pad, y+pad), bg, -1)
    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)

def draw_angle_arc(img, cx, cy, angle, color=YELLOW, radius=45):
    """Draw a small arc annotation showing the joint angle value."""
    cv2.circle(img, (cx, cy), radius, color, 2, cv2.LINE_AA)
    label = f"{int(angle)}\xb0"
    put_text_bg(img, label, (cx - 18, cy + 5), scale=0.55, color=color)


# ── Landmark names for annotation ──────────────────────────────────────────────
LANDMARK_NAMES = {
    0:  "NOSE",          11: "L.SHOULDER",   12: "R.SHOULDER",
    13: "L.ELBOW",       14: "R.ELBOW",       15: "L.WRIST",
    16: "R.WRIST",       23: "L.HIP",         24: "R.HIP",
    25: "L.KNEE",        26: "R.KNEE",        27: "L.ANKLE",
    28: "R.ANKLE",
}

TRACKED_POINTS = list(LANDMARK_NAMES.keys())

# ── Exercise angle configurations ──────────────────────────────────────────────
EXERCISES = {
    "Bicep Curl":     {"joints": (11, 13, 15), "down": 160, "up": 45,  "side": "LEFT"},
    "Squat":          {"joints": (23, 25, 27), "down": 170, "up": 90,  "side": "LEFT"},
    "Shoulder Press": {"joints": (13, 11, 23), "down": 160, "up": 60,  "side": "LEFT"},
    "Lateral Raise":  {"joints": (13, 11, 23), "down": 170, "up": 75,  "side": "LEFT"},
    "Push-Up":        {"joints": (11, 13, 15), "down": 160, "up": 70,  "side": "LEFT"},
}

exercise_keys = list(EXERCISES.keys())
ex_idx = 0


# ── Rep counter state ──────────────────────────────────────────────────────────
rep_count  = 0
stage      = None       # "down" / "up"


def update_reps(angle, down_thresh, up_thresh):
    global rep_count, stage
    new_rep = False
    if angle > down_thresh:
        stage = "down"
    if angle < up_thresh and stage == "down":
        stage = "up"
        rep_count += 1
        new_rep = True
    return new_rep


# ── Preprocessing pipeline steps ──────────────────────────────────────────────
def preprocess_frame(raw):
    """
    Applies the full preprocessing pipeline and returns annotated steps.
    Returns dict of labelled intermediate frames for display.
    """
    # Step 1: Resize to standard resolution
    resized   = cv2.resize(raw, (640, 480))

    # Step 2: Horizontal flip (mirror for self-view)
    flipped   = cv2.flip(resized, 1)

    # Step 3: Grayscale conversion
    gray      = cv2.cvtColor(flipped, cv2.COLOR_BGR2GRAY)
    gray_bgr  = cv2.cvtColor(gray,    cv2.COLOR_GRAY2BGR)

    # Step 4: Gaussian blur (noise reduction)
    blurred   = cv2.GaussianBlur(flipped, (7, 7), 1.5)

    # Step 5: Edge map (Canny) for movement detection
    edges     = cv2.Canny(gray, 50, 150)
    edges_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    return {
        "1_Resized"      : resized,
        "2_Mirrored"     : flipped,
        "3_Grayscale"    : gray_bgr,
        "4_GaussBlur"    : blurred,
        "5_EdgeMap(Canny)": edges_bgr,
    }


def draw_landmark_panel(img, landmarks, w, h, selected_joints):
    """Draw 3-D coordinate table for key landmarks as panel overlay."""
    panel_x, panel_y = w - 260, 50
    panel_h = len(TRACKED_POINTS) * 18 + 30
    overlay = img.copy()
    cv2.rectangle(overlay, (panel_x - 8, panel_y - 22),
                  (panel_x + 255, panel_y + panel_h), (10, 10, 30), -1)
    cv2.addWeighted(overlay, 0.80, img, 0.20, 0, img)

    cv2.putText(img, "LANDMARK COORDINATES", (panel_x, panel_y - 6),
                FONT_SMALL, 0.38, CYAN, 1, cv2.LINE_AA)
    cv2.putText(img, "  ID   NAME          X     Y     Z",
                (panel_x, panel_y + 8), FONT_SMALL, 0.32, (150,150,150), 1)

    for row, idx in enumerate(TRACKED_POINTS):
        lm = landmarks[idx]
        name = LANDMARK_NAMES[idx]
        col = YELLOW if idx in selected_joints else WHITE
        text = (f"  {idx:02d}  {name:<12s}  "
                f"{lm.x:.3f} {lm.y:.3f} {lm.z:+.3f}")
        cv2.putText(img, text,
                    (panel_x, panel_y + 24 + row * 18),
                    FONT_SMALL, 0.33, col, 1, cv2.LINE_AA)


def draw_hud(img, angle, rep_count, stage, exercise, fps, frame_num, elapsed):
    """Draw the main HUD overlay on the pose frame."""
    h, w = img.shape[:2]

    # Top bar
    cv2.rectangle(img, (0, 0), (w, 55), (10, 10, 30), -1)
    cv2.putText(img, "MODULE 1 — VIDEO ACQUISITION & PREPROCESSING",
                (10, 22), FONT_SMALL, 0.55, CYAN, 1, cv2.LINE_AA)
    cv2.putText(img, f"FitPulse Pro  |  FPS: {fps:4.1f}  |  Frame: {frame_num:05d}  |  t: {elapsed:.1f}s",
                (10, 44), FONT_SMALL, 0.42, (150, 180, 200), 1, cv2.LINE_AA)

    # Bottom bar
    cv2.rectangle(img, (0, h - 80), (w, h), (10, 10, 30), -1)

    # Rep counter box
    cv2.rectangle(img, (10, h - 74), (160, h - 6), (30, 70, 30), -1)
    cv2.rectangle(img, (10, h - 74), (160, h - 6), GREEN, 2)
    cv2.putText(img, "REPS", (18, h - 56), FONT, 0.5, GREEN, 1)
    cv2.putText(img, str(rep_count), (30, h - 16), FONT, 1.8, WHITE, 3)

    # Stage box
    stage_col = GREEN if stage == "up" else ORANGE
    cv2.rectangle(img, (175, h - 74), (310, h - 6), (20, 20, 50), -1)
    cv2.rectangle(img, (175, h - 74), (310, h - 6), stage_col, 2)
    cv2.putText(img, "STAGE", (183, h - 56), FONT, 0.5, stage_col, 1)
    cv2.putText(img, (stage or "READY").upper(), (183, h - 14),
                FONT, 0.8, WHITE, 2)

    # Angle box
    cv2.rectangle(img, (325, h - 74), (470, h - 6), (20, 20, 50), -1)
    cv2.rectangle(img, (325, h - 74), (470, h - 6), YELLOW, 2)
    cv2.putText(img, "ANGLE", (333, h - 56), FONT, 0.5, YELLOW, 1)
    cv2.putText(img, f"{int(angle)}\xb0", (333, h - 14), FONT, 1.0, WHITE, 2)

    # Exercise name
    cv2.putText(img, f"Exercise: {exercise}", (490, h - 40),
                FONT_SMALL, 0.6, CYAN, 1, cv2.LINE_AA)
    cv2.putText(img, "Q=quit  S=screenshot  E=switch exercise",
                (490, h - 14), FONT_SMALL, 0.38, (130, 130, 130), 1, cv2.LINE_AA)

    # Angle bar
    pct = int(np.clip((180 - angle) / 150 * 100, 0, 100))
    bx, by, bw, bh2 = 10, h - 90, w - 20, 8
    cv2.rectangle(img, (bx, by), (bx + bw, by + bh2), (40, 40, 40), -1)
    cv2.rectangle(img, (bx, by), (bx + int(bw * pct / 100), by + bh2), YELLOW, -1)


def build_preprocessing_strip(steps_dict, strip_w=640):
    """Tile the preprocessing steps into a single horizontal strip."""
    n   = len(steps_dict)
    th  = 110   # thumbnail height
    tw  = strip_w // n
    strip = np.zeros((th + 22, strip_w, 3), dtype=np.uint8)
    strip[:] = (15, 15, 25)

    for i, (label, frame) in enumerate(steps_dict.items()):
        thumb = cv2.resize(frame, (tw - 4, th - 4))
        x     = i * tw + 2
        strip[2:th - 2, x:x + tw - 4] = thumb
        cv2.rectangle(strip, (x - 1, 1), (x + tw - 5, th - 1), CYAN, 1)
        # Label
        short = label.split("_", 1)[-1][:14]
        cv2.putText(strip, short, (x + 3, th + 14),
                    FONT_SMALL, 0.32, CYAN, 1, cv2.LINE_AA)
    return strip


def main():
    global rep_count, stage, ex_idx

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    pose = mp_pose.Pose(
        model_complexity           = 1,
        smooth_landmarks           = True,
        enable_segmentation        = False,
        min_detection_confidence   = 0.55,
        min_tracking_confidence    = 0.55
    )

    frame_num   = 0
    fps         = 0
    fps_timer   = time.time()
    fps_counter = 0
    start_time  = time.time()
    last_angle  = 90.0
    flash_frames = 0

    print("\n" + "="*70)
    print("  MODULE 1 — Video Acquisition & Preprocessing")
    print("  FitPulse Pro  |  Cognitive-Physical Fitness System")
    print("="*70)
    print("  Controls:")
    print("    Q  — Quit")
    print("    S  — Save screenshot to output/")
    print("    E  — Switch exercise")
    print("    R  — Reset rep counter")
    print("="*70 + "\n")

    while True:
        ret, raw = cap.read()
        if not ret:
            print("[MOD1] Camera read failed. Check webcam connection.")
            break

        frame_num   += 1
        fps_counter += 1
        elapsed      = time.time() - start_time

        # ── FPS ───────────────────────────────────────────────────────────────
        if time.time() - fps_timer >= 1.0:
            fps         = fps_counter
            fps_counter = 0
            fps_timer   = time.time()

        # ── Preprocessing pipeline ────────────────────────────────────────────
        steps  = preprocess_frame(raw)
        frame  = steps["2_Mirrored"].copy()   # work on the mirrored frame
        h, w   = frame.shape[:2]

        # ── Pose estimation ───────────────────────────────────────────────────
        rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        exercise = exercise_keys[ex_idx]
        ex_cfg   = EXERCISES[exercise]
        j0, j1, j2 = ex_cfg["joints"]
        angle    = last_angle

        pose_frame = frame.copy()

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            # Custom landmark drawing
            mp_draw.draw_landmarks(
                pose_frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                mp_draw.DrawingSpec(color=(60, 255, 120), thickness=2, circle_radius=4),
                mp_draw.DrawingSpec(color=(0, 180, 255),  thickness=2, circle_radius=2),
            )

            # Compute angle
            a_xy = lm_xy(lm, j0, w, h)
            b_xy = lm_xy(lm, j1, w, h)
            c_xy = lm_xy(lm, j2, w, h)
            angle     = angle_3pts(a_xy, b_xy, c_xy)
            last_angle = angle

            # Highlight tracked joints
            for pt, col in [(a_xy, GREEN), (b_xy, YELLOW), (c_xy, GREEN)]:
                cv2.circle(pose_frame, pt, 10, col, -1, cv2.LINE_AA)
                cv2.circle(pose_frame, pt, 13, WHITE, 2, cv2.LINE_AA)

            # Draw angle lines
            cv2.line(pose_frame, b_xy, a_xy, YELLOW, 3, cv2.LINE_AA)
            cv2.line(pose_frame, b_xy, c_xy, YELLOW, 3, cv2.LINE_AA)
            draw_angle_arc(pose_frame, b_xy[0], b_xy[1], angle)

            # Rep counting
            new_rep = update_reps(angle, ex_cfg["down"], ex_cfg["up"])
            if new_rep:
                flash_frames = 8

            # Landmark coordinate panel
            draw_landmark_panel(pose_frame, lm, w, h, {j0, j1, j2})

        # ── Flash on new rep ──────────────────────────────────────────────────
        if flash_frames > 0:
            overlay = pose_frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), GREEN, -1)
            cv2.addWeighted(overlay, 0.18, pose_frame, 0.82, 0, pose_frame)
            flash_frames -= 1

        # ── HUD ───────────────────────────────────────────────────────────────
        draw_hud(pose_frame, angle, rep_count, stage, exercise,
                 fps, frame_num, elapsed)

        # ── Preprocessing strip ───────────────────────────────────────────────
        strip = build_preprocessing_strip(steps, strip_w=w)

        # ── Module label ──────────────────────────────────────────────────────
        label_bar = np.zeros((28, w, 3), dtype=np.uint8)
        label_bar[:] = (8, 8, 20)
        cv2.putText(label_bar,
                    "PREPROCESSING PIPELINE — Steps 1-5",
                    (8, 19), FONT_SMALL, 0.45, CYAN, 1, cv2.LINE_AA)

        # ── Stack vertically: pose view + label + strip ───────────────────────
        display = np.vstack([pose_frame, label_bar, strip])
        cv2.imshow(WIN_TITLE, display)

        # ── Key handling ──────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break

        elif key == ord('s'):
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"output/mod1_capture_{ts}.png"
            cv2.imwrite(path, display)
            print(f"[MOD1] Screenshot saved → {path}")

        elif key == ord('e'):
            ex_idx = (ex_idx + 1) % len(exercise_keys)
            rep_count = 0; stage = None
            print(f"[MOD1] Switched to: {exercise_keys[ex_idx]}")

        elif key == ord('r'):
            rep_count = 0; stage = None
            print("[MOD1] Rep counter reset")

    cap.release()
    pose.close()
    cv2.destroyAllWindows()

    print(f"\n[MOD1] Session ended — {frame_num} frames processed  |  "
          f"Total reps: {rep_count}")


if __name__ == "__main__":
    main()
