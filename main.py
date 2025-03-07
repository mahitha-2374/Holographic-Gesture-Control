import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logs

import sys
from contextlib import contextmanager
import cv2
import time
import math
import numpy as np
import pyautogui
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import handtracking  # Ensure handtracking.py is in the same directory

# Suppress stderr logs during MediaPipe initialization
@contextmanager
def suppress_stderr():
    with open(os.devnull, 'w') as devnull:
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stderr = old_stderr

with suppress_stderr():
    import mediapipe as mp

# Initialize hand detector
hand_tracker = handtracking.HandDetector(maxHands=1, detectionCon=0.85, trackCon=0.8)

# Camera settings
FRAME_WIDTH, FRAME_HEIGHT = 640, 480
cap = cv2.VideoCapture(0)  # Use 0 for the default webcam
if not cap.isOpened():
    print("Error: Could not open camera. Please check if the camera is connected and not in use by another application.")
    exit()

cap.set(3, FRAME_WIDTH)
cap.set(4, FRAME_HEIGHT)

# Timeout settings
timeout = 10  # Timeout in seconds
start_time = time.time()

# Audio setup
audio_device = AudioUtilities.GetSpeakers()
audio_interface = audio_device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume_control = cast(audio_interface, POINTER(IAudioEndpointVolume))
vol_range = volume_control.GetVolumeRange()

MIN_VOL, MAX_VOL = -63, vol_range[1]
HAND_MIN_DIST, HAND_MAX_DIST = 50, 200

# UI elements
vol_bar = 400
vol_percentage = 0
current_vol = 0
highlight_color = (0, 215, 255)

tip_ids = [4, 8, 12, 16, 20]
current_mode = ''
is_active = 0
pyautogui.FAILSAFE = False

def display_text(frame, text, position=(250, 450), color=(0, 255, 255)):
    cv2.putText(frame, text, position, cv2.FONT_HERSHEY_COMPLEX_SMALL, 3, color, 3)

prev_time = 0

while True:
    success, frame = cap.read()
    if not success:
        print("Failed to capture frame.")
        if time.time() - start_time > timeout:
            print("Timeout: Camera not responding.")
            break
        continue

    # Reset the timeout timer if a frame is captured
    start_time = time.time()

    # Process the frame
    frame = hand_tracker.findHands(frame)
    landmarks_list = hand_tracker.findPosition(frame, draw=False)
    fingers_state = []

    if landmarks_list and len(landmarks_list) >= 21:  # Ensure there are enough landmarks
        # Thumb detection
        fingers_state.append(1 if landmarks_list[tip_ids[0]][1] > landmarks_list[tip_ids[0] - 1][1] else 0)
        
        # Other fingers detection
        for i in range(1, 5):
            fingers_state.append(1 if landmarks_list[tip_ids[i]][2] < landmarks_list[tip_ids[i] - 2][2] else 0)

        # Mode switching
        if fingers_state == [0, 0, 0, 0, 0] and is_active == 0:
            current_mode = 'N'
        elif fingers_state in [[0, 1, 0, 0, 0], [0, 1, 1, 0, 0]] and is_active == 0:
            current_mode, is_active = 'Scroll', 1
        elif fingers_state == [1, 1, 0, 0, 0] and is_active == 0:
            current_mode, is_active = 'Volume', 1
        elif fingers_state == [1, 1, 1, 1, 1] and is_active == 0:
            current_mode, is_active = 'Cursor', 1

    # Scroll Mode
    if current_mode == 'Scroll':
        display_text(frame, current_mode)
        cv2.rectangle(frame, (200, 410), (245, 460), (255, 255, 255), cv2.FILLED)
        if fingers_state == [0, 1, 0, 0, 0]:
            display_text(frame, 'U', (200, 455), (0, 255, 0))
            pyautogui.scroll(300)
        elif fingers_state == [0, 1, 1, 0, 0]:
            display_text(frame, 'D', (200, 455), (0, 0, 255))
            pyautogui.scroll(-300)
        elif fingers_state == [0, 0, 0, 0, 0]:
            is_active, current_mode = 0, 'N'
    
    # Volume Mode
    elif current_mode == 'Volume':
        display_text(frame, current_mode)
        if fingers_state and fingers_state[-1] == 1:  # Check if fingers_state is not empty
            is_active, current_mode = 0, 'N'
        else:
            if landmarks_list and len(landmarks_list) >= 21:  # Ensure there are enough landmarks
                x1, y1 = landmarks_list[4][1], landmarks_list[4][2]
                x2, y2 = landmarks_list[8][1], landmarks_list[8][2]
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                
                cv2.circle(frame, (x1, y1), 10, highlight_color, cv2.FILLED)
                cv2.circle(frame, (x2, y2), 10, highlight_color, cv2.FILLED)
                cv2.line(frame, (x1, y1), (x2, y2), highlight_color, 3)
                cv2.circle(frame, (cx, cy), 8, highlight_color, cv2.FILLED)
                
                hand_distance = math.hypot(x2 - x1, y2 - y1)
                current_vol = np.interp(hand_distance, [HAND_MIN_DIST, HAND_MAX_DIST], [MIN_VOL, MAX_VOL])
                vol_bar = np.interp(current_vol, [MIN_VOL, MAX_VOL], [400, 150])
                vol_percentage = np.interp(current_vol, [MIN_VOL, MAX_VOL], [0, 100])
                
                volume_control.SetMasterVolumeLevel(current_vol, None)
                if hand_distance < 50:
                    cv2.circle(frame, (cx, cy), 11, (0, 0, 255), cv2.FILLED)
                
                cv2.rectangle(frame, (30, 150), (55, 400), (209, 206, 0), 3)
                cv2.rectangle(frame, (30, int(vol_bar)), (55, 400), (215, 255, 127), cv2.FILLED)
                cv2.putText(frame, f'{int(vol_percentage)}%', (25, 430), cv2.FONT_HERSHEY_COMPLEX, 0.9, (209, 206, 0), 3)
    
    # Cursor Mode
    elif current_mode == 'Cursor':
        display_text(frame, current_mode)
        cv2.rectangle(frame, (110, 20), (620, 350), (255, 255, 255), 3)
        if fingers_state and fingers_state[1:] == [0, 0, 0, 0]:  # Check if fingers_state is not empty
            is_active, current_mode = 0, 'N'
        else:
            if landmarks_list and len(landmarks_list) >= 21:  # Ensure there are enough landmarks
                x, y = landmarks_list[8][1], landmarks_list[8][2]
                screen_width, screen_height = pyautogui.size()
                mapped_x = int(np.interp(x, [110, 620], [0, screen_width - 1]))
                mapped_y = int(np.interp(y, [20, 350], [0, screen_height - 1]))
                pyautogui.moveTo(mapped_x, mapped_y)
                if fingers_state and fingers_state[0] == 0:  # Check if fingers_state is not empty
                    pyautogui.click()
    
    # Display FPS
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time + 0.01)
    prev_time = curr_time
    cv2.putText(frame, f'FPS: {int(fps)}', (480, 50), cv2.FONT_ITALIC, 1, (255, 0, 0), 2)
    cv2.imshow('Hand Gesture Control', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()