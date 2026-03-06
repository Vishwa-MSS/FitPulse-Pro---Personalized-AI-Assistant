import cv2
import mediapipe as mp
import numpy as np

cap = cv2.VideoCapture(0)

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)

# Canvas
canvas = None
prev_x, prev_y = 0, 0

# Colors (BGR)
colors = [
    (255, 0, 255),   # Purple
    (255, 0, 0),     # Blue
    (0, 255, 0),     # Green
    (0, 255, 255),   # Yellow
    (0, 0, 0)        # Eraser
]
color_names = ["PURPLE", "BLUE", "GREEN", "YELLOW", "ERASER"]
current_color = colors[0]

def fingers_up(hand):
    fingers = []
    fingers.append(hand.landmark[8].y < hand.landmark[6].y)    # index
    fingers.append(hand.landmark[12].y < hand.landmark[10].y)  # middle
    return fingers

def draw_palette(img):
    h, w, _ = img.shape
    box_w = w // len(colors)
    for i, col in enumerate(colors):
        x1 = i * box_w
        x2 = (i + 1) * box_w
        cv2.rectangle(img, (x1, 0), (x2, 60), col, -1)
        cv2.putText(img, color_names[i], (x1 + 10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

while True:
    success, frame = cap.read()
    if not success:
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    if canvas is None:
        canvas = np.zeros((h, w, 3), dtype=np.uint8)

    draw_palette(frame)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)

    mode = "NONE"

    if results.multi_hand_landmarks:
        for hand in results.multi_hand_landmarks:

            mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)

            index_up, middle_up = fingers_up(hand)

            x = int(hand.landmark[8].x * w)
            y = int(hand.landmark[8].y * h)

            # Selection mode
            if index_up and middle_up:
                mode = "SELECT"
                prev_x, prev_y = 0, 0

                if y < 60:
                    box_w = w // len(colors)
                    idx = x // box_w
                    if idx < len(colors):
                        current_color = colors[idx]

                cv2.circle(frame, (x, y), 15, current_color, cv2.FILLED)

            # Draw / Erase mode
            elif index_up and not middle_up:
                mode = "DRAW"
                cv2.circle(frame, (x, y), 10, current_color, cv2.FILLED)

                if prev_x == 0 and prev_y == 0:
                    prev_x, prev_y = x, y

                thickness = 40 if current_color == (0, 0, 0) else 8
                cv2.line(canvas, (prev_x, prev_y), (x, y), current_color, thickness)
                prev_x, prev_y = x, y

            else:
                prev_x, prev_y = 0, 0

    else:
        prev_x, prev_y = 0, 0

    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    _, inv = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY_INV)
    inv = cv2.cvtColor(inv, cv2.COLOR_GRAY2BGR)
    frame = cv2.bitwise_and(frame, inv)
    frame = cv2.bitwise_or(frame, canvas)

    cv2.putText(frame, f"Mode: {mode}",
                (10, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    cv2.putText(frame,
                "Index: Draw | Index+Middle: Select Color | C: Clear | Q: Quit",
                (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.imshow("Air Canvas", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('c'):
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()



