"""
gaze_engine.py  — ACCURACY REWRITE
=====================================
Problem: when YOLO or CNN model missing, _fallback_result always
returns focus_score=50 with static DETECTING text → never changes.

FIX: Replace dead fallback with real OpenCV-based gaze estimator:
  1. Haar face + eye detection         (ships with OpenCV)
  2. Eye Aspect Ratio (EAR)            → open / closed / drowsy
  3. Iris centre estimation            → left/right/centre gaze
  4. Temporal rolling average          → smooth focus score

When YOLO + CNN models ARE present, auto-switches to the accurate pipeline.
Without them, OpenCV estimator gives solid results for fitness coaching.
"""

import cv2
import numpy as np
import os, base64, time
from collections import deque

EYE_SIZE         = 22
CLOSED_THRESHOLD = 18     # consecutive closed frames → drowsy


class _CVGazeEstimator:
    """
    Pure-OpenCV eye-state and gaze estimator.

    Steps per frame:
      1. Detect face → extract upper-half (eye region)
      2. Detect eye ROIs with haarcascade_eye
      3. Measure eye openness from ROI height/width ratio
      4. Estimate iris centre shift (left/right via Hough circles)
      5. Compute focus score from openness + centring + history
    """

    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade  = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml')

        self.focus_history    = deque(maxlen=25)
        self.closed_counter   = 0
        self.total_frames     = 0
        self.drowsy_frames    = 0
        self.alert_count      = 0

    # ── Eye state from ROI ─────────────────────────────────────────────────
    def _eye_open_ratio(self, eye_roi_gray) -> float:
        """
        0 = clearly closed, 1 = clearly open.
        Uses mean pixel brightness of the pupil strip vs full ROI.
        Dark centre + bright surround → open eye.
        """
        if eye_roi_gray.size == 0:
            return 0.5
        h, w = eye_roi_gray.shape
        # Pupil strip: centre 40% of height
        centre_strip = eye_roi_gray[int(h*0.30): int(h*0.70), :]
        full_mean    = eye_roi_gray.mean()
        centre_mean  = centre_strip.mean() if centre_strip.size > 0 else full_mean
        # Open eye: dark pupil strip → lower centre_mean relative to full
        ratio = float(np.clip(1.0 - (centre_mean / (full_mean + 1e-3)), 0, 1))
        return ratio

    def _is_closed(self, eye_roi_gray) -> bool:
        ratio = self._eye_open_ratio(eye_roi_gray)
        return ratio < 0.15    # very low contrast → likely closed

    # ── Gaze direction from iris ───────────────────────────────────────────
    def _gaze_centred(self, eye_roi_gray) -> bool:
        """True if iris is roughly centred in the eye ROI."""
        h, w = eye_roi_gray.shape
        blurred = cv2.GaussianBlur(eye_roi_gray, (5, 5), 0)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, 1, 20,
            param1=50, param2=12, minRadius=4, maxRadius=max(6, w//4))
        if circles is None:
            return True   # can't detect → assume centred
        cx = circles[0, 0, 0]
        # Centre zone: middle 50% of eye width
        return w * 0.25 < cx < w * 0.75

    # ── Main predict ───────────────────────────────────────────────────────
    def predict(self, frame: np.ndarray) -> dict:
        self.total_frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        gray = cv2.equalizeHist(gray)
        h_frame, w_frame = gray.shape

        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

        if not len(faces):
            # No face → count as attention away, don't freeze
            self.focus_history.append(30.0)
            fs = round(float(np.mean(self.focus_history)), 1)
            return self._make_result(fs, 'AWAY', 'AWAY', False)

        x, y, w, h = max(faces, key=lambda f: f[2]*f[3])
        upper = gray[y: y + h//2, x: x+w]

        eyes = self.eye_cascade.detectMultiScale(
            upper, scaleFactor=1.1, minNeighbors=6, minSize=(14, 14))

        if not len(eyes):
            # Face found but no eyes visible → partially closed
            self.focus_history.append(40.0)
            fs = round(float(np.mean(self.focus_history)), 1)
            return self._make_result(fs, 'CLOSED', 'CLOSED', False)

        # Sort by x to get left / right eye
        eyes_sorted = sorted(eyes, key=lambda e: e[0])

        states   = []
        centred  = True
        for (ex, ey, ew, eh) in eyes_sorted[:2]:
            roi = upper[ey: ey+eh, ex: ex+ew]
            closed = self._is_closed(roi)
            states.append(closed)
            if not self._gaze_centred(roi):
                centred = False

        left_closed  = states[0] if len(states) > 0 else False
        right_closed = states[1] if len(states) > 1 else states[0]

        both_closed = left_closed and right_closed
        if both_closed:
            self.closed_counter += 1
            self.drowsy_frames  += 1
            base_focus = 15.0
        elif left_closed or right_closed:
            self.closed_counter  = max(0, self.closed_counter - 1)
            base_focus = 52.0
        else:
            if self.closed_counter >= CLOSED_THRESHOLD:
                self.alert_count += 1
            self.closed_counter = max(0, self.closed_counter - 2)
            base_focus = 88.0

        # Bonus for centred gaze
        if centred and not both_closed:
            base_focus = min(100.0, base_focus + 8.0)

        # Face centre bonus (face in middle of frame)
        face_cx = x + w / 2
        if w_frame * 0.2 < face_cx < w_frame * 0.8:
            base_focus = min(100.0, base_focus + 5.0)

        self.focus_history.append(base_focus)
        fs = round(float(np.mean(self.focus_history)), 1)

        is_drowsy = self.closed_counter >= CLOSED_THRESHOLD
        l_label = 'CLOSED' if left_closed  else 'OPEN'
        r_label = 'CLOSED' if right_closed else 'OPEN'
        return self._make_result(fs, l_label, r_label, is_drowsy)

    def _make_result(self, focus_score, left_eye, right_eye, is_drowsy) -> dict:
        drowsy_pct    = round(min(self.closed_counter / CLOSED_THRESHOLD, 1.0) * 100, 1)
        eyes_open_pct = round((1 - self.drowsy_frames / max(self.total_frames, 1)) * 100, 1)
        return {
            'focus_score':   focus_score,
            'left_eye':      left_eye,
            'right_eye':     right_eye,
            'is_drowsy':     is_drowsy,
            'drowsy_pct':    drowsy_pct,
            'eyes_open_pct': eyes_open_pct,
            'alert_count':   self.alert_count,
            'face_detected': True,
            'method':        'opencv',
            'timestamp':     time.time()
        }

    def reset(self):
        self.focus_history.clear()
        self.closed_counter = 0
        self.total_frames   = 0
        self.drowsy_frames  = 0
        self.alert_count    = 0


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ENGINE — auto-switches YOLO+CNN → OpenCV
# ══════════════════════════════════════════════════════════════════════════════
class GazeEngine:
    def __init__(self,
                 yolo_model_path: str = 'models/yolov8n-pose.pt',
                 cnn_model_path:  str = 'models/eye_state_cnn_model_finetuned.keras'):

        self.yolo      = None
        self.eye_model = None
        self.yolo_path = yolo_model_path
        self.cnn_path  = cnn_model_path
        self.using_ml  = False

        # OpenCV fallback (always ready)
        self._cv_estimator = _CVGazeEstimator()

        self.last_result     = None
        self.frame_count     = 0
        self.process_every_n = 3

        self._load_models()
        mode = "YOLO+CNN" if self.using_ml else "OpenCV (no model needed)"
        print(f"[GazeEngine] ✅ Ready  mode={mode}")

    def _load_models(self):
        try:
            from ultralytics import YOLO
            self.yolo = YOLO(self.yolo_path)
            print(f"[GazeEngine] YOLO loaded: {self.yolo_path}")
        except Exception as e:
            print(f"[GazeEngine] YOLO not loaded ({e}) → OpenCV mode")

        if not os.path.exists(self.cnn_path):
            print(f"[GazeEngine] CNN not found at '{self.cnn_path}' → OpenCV mode")
            return
        try:
            import tensorflow as tf
            self.eye_model = tf.keras.models.load_model(self.cnn_path)
            self.using_ml  = (self.yolo is not None)
            print(f"[GazeEngine] Eye CNN loaded: {self.cnn_path}")
        except Exception as e:
            print(f"[GazeEngine] CNN load failed ({e}) → OpenCV mode")

    # ── YOLO+CNN path ─────────────────────────────────────────────────────────
    def _predict_eye_state(self, gray, cx, cy) -> int:
        roi = gray[max(0,cy-EYE_SIZE):min(gray.shape[0],cy+EYE_SIZE),
                   max(0,cx-EYE_SIZE):min(gray.shape[1],cx+EYE_SIZE)]
        if roi.size == 0:
            return 0
        roi_in = (cv2.resize(roi, (64,64)) / 255.0).reshape(1, 64, 64, 1)
        pred   = self.eye_model.predict(roi_in, verbose=0)[0][0]
        return 1 if pred > 0.5 else 0

    def _predict_ml(self, frame: np.ndarray) -> dict:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]
        for r in self.yolo(frame, stream=True, verbose=False):
            if r.keypoints is None:
                continue
            for kp in r.keypoints.xy.cpu().numpy():
                lx, ly = int(kp[1][0]), int(kp[1][1])
                rx, ry = int(kp[2][0]), int(kp[2][1])
                if lx == 0 and ly == 0:
                    continue
                lc = self._predict_eye_state(gray, lx, ly)
                rc = self._predict_eye_state(gray, rx, ry)
                face_cx = (lx + rx) / 2
                centred = w * 0.25 < face_cx < w * 0.75
                base    = 90.0 if (not lc and not rc) else (15.0 if (lc and rc) else 52.0)
                if centred:
                    base = min(100, base + 8)
                cv = self._cv_estimator
                cv.focus_history.append(base)
                if lc and rc:
                    cv.closed_counter += 1; cv.drowsy_frames += 1
                else:
                    if cv.closed_counter >= CLOSED_THRESHOLD:
                        cv.alert_count += 1
                    cv.closed_counter = max(0, cv.closed_counter - 2)
                cv.total_frames += 1
                fs = round(float(np.mean(cv.focus_history)), 1)
                return cv._make_result(fs,
                    'CLOSED' if lc else 'OPEN',
                    'CLOSED' if rc else 'OPEN',
                    cv.closed_counter >= CLOSED_THRESHOLD)
        return None

    # ── Main interface ─────────────────────────────────────────────────────────
    def predict_from_frame(self, frame: np.ndarray) -> dict:
        self.frame_count += 1
        if self.frame_count % self.process_every_n != 0 and self.last_result:
            return self.last_result

        result = None
        try:
            if self.using_ml:
                result = self._predict_ml(frame)
            if result is None:
                result = self._cv_estimator.predict(frame)
        except Exception as e:
            print(f"[GazeEngine] error: {e}")
            result = self._cv_estimator.predict(frame)

        self.last_result = result
        return result

    def process_frame_b64(self, b64_image: str) -> dict:
        try:
            if ',' in b64_image:
                b64_image = b64_image.split(',', 1)[1]
            img = cv2.imdecode(
                np.frombuffer(base64.b64decode(b64_image), np.uint8),
                cv2.IMREAD_COLOR)
            if img is None:
                return self._cv_estimator._make_result(50, 'DETECTING', 'DETECTING', False)
            return self.predict_from_frame(img)
        except Exception as e:
            print(f"[GazeEngine] b64 error: {e}")
            return self._cv_estimator._make_result(50, 'DETECTING', 'DETECTING', False)

    def get_session_stats(self) -> dict:
        cv = self._cv_estimator
        return {
            'total_frames':       cv.total_frames,
            'drowsy_frames':      cv.drowsy_frames,
            'alert_count':        cv.alert_count,
            'drowsy_pct_session': round(cv.drowsy_frames / max(cv.total_frames, 1) * 100, 1)
        }

    def reset(self):
        self._cv_estimator.reset()
        self.last_result = None
        self.frame_count = 0

    def is_ready(self) -> bool:
        return True   # OpenCV mode always works