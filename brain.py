"""
brain.py — Hafta 4: YOLOv8 Entegrasyonu + Final
──────────────────────────────────────────────────
Protokol:
  C++ → Python : 200×200 RGBA ham piksel (160_000 byte)
  Python → C++ : "STOP\n"  veya  angle string "12.45\n"

Karar Önceliği:
  1. Engel %30+ ekranı kaplıyorsa → STOP
  2. Engel yoksa → PID ile şerit açısı gönder
"""

import socket
import time
import json
import numpy as np
import cv2
from ultralytics import YOLO

HOST = "127.0.0.1"
PORT = 5000

ROI_W = 200
ROI_H = 200
IMAGE_SIZE = ROI_W * ROI_H * 4   # RGBA

# Engel eşiği: BBox alanı ekranın bu yüzdesini geçerse STOP
OBSTACLE_AREA_THRESHOLD = 0.30   # %30

# YOLOv8 modelini yükle (nano = en hızlı)
MODEL_PATH = "yolov8n.pt"


# ══════════════════════════════════════════════
# TCP HELPER
# ══════════════════════════════════════════════
def receive_all(sock: socket.socket, size: int) -> bytes | None:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


# ══════════════════════════════════════════════
# PID CONTROLLER
# ══════════════════════════════════════════════
class PIDController:
    def __init__(self, kp: float = 0.4, ki: float = 0.0, kd: float = 0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.previous_error = 0.0
        self.integral = 0.0

    def compute(self, error: float, dt: float) -> float:
        if dt <= 0:
            dt = 1e-6
        self.integral += error * dt
        derivative = (error - self.previous_error) / dt
        self.previous_error = error
        output = (self.kp * error
                  + self.ki * self.integral
                  + self.kd * derivative)
        return float(np.clip(output, -30.0, 30.0))

    def reset(self):
        self.previous_error = 0.0
        self.integral = 0.0


# ══════════════════════════════════════════════
# FRAME PARSING
# ══════════════════════════════════════════════
def bytes_to_frames(rgba_bytes: bytes):
    arr  = np.frombuffer(rgba_bytes, dtype=np.uint8)
    rgba = arr.reshape((ROI_H, ROI_W, 4))
    bgr  = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)
    return rgba, bgr, gray


# ══════════════════════════════════════════════
# LANE DETECTION
# ══════════════════════════════════════════════
def detect_lanes(gray: np.ndarray, pid: PIDController, dt: float):
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, 50, 150)

    mask = np.zeros_like(edges)
    mask[ROI_H // 2:, :] = 255
    masked = cv2.bitwise_and(edges, mask)

    lines = cv2.HoughLinesP(
        masked, rho=1, theta=np.pi / 180,
        threshold=20, minLineLength=20, maxLineGap=30
    )

    left_xs, right_xs = [], []
    lane_debug = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 == x1:
                continue
            slope = (y2 - y1) / (x2 - x1)
            if abs(slope) < 0.3:
                continue
            if slope < 0:
                left_xs.extend([x1, x2])
                cv2.line(lane_debug, (x1, y1), (x2, y2), (255, 80, 0), 2)
            else:
                right_xs.extend([x1, x2])
                cv2.line(lane_debug, (x1, y1), (x2, y2), (0, 80, 255), 2)

    cx = ROI_W / 2.0
    left_x  = float(np.mean(left_xs))  if left_xs  else None
    right_x = float(np.mean(right_xs)) if right_xs else None

    if left_x is not None and right_x is not None:
        lane_cx = (left_x + right_x) / 2.0
    elif left_x is not None:
        lane_cx = left_x + 50.0
    elif right_x is not None:
        lane_cx = right_x - 50.0
    else:
        lane_cx = cx

    offset = cx - lane_cx
    angle  = pid.compute(offset, dt)

    cv2.line(lane_debug, (int(lane_cx), ROI_H // 2), (int(lane_cx), ROI_H), (0, 255, 0), 2)
    cv2.line(lane_debug, (int(cx),      ROI_H // 2), (int(cx),      ROI_H), (0, 255, 255), 1)
    cv2.putText(lane_debug, f"offset:{offset:+.1f}  angle:{angle:+.2f}",
                (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    return angle, lane_debug


# ══════════════════════════════════════════════
# YOLO OBSTACLE DETECTION
# ══════════════════════════════════════════════
def detect_obstacles_yolo(bgr: np.ndarray, model: YOLO):
    """
    YOLOv8 ile nesne tespiti yapar.
    BBox alanı ROI alanının %30'unu geçiyorsa engel var sayar.
    Döndürür: (obstacle_detected: bool, speed: int, debug_image)
    """
    roi_area = ROI_W * ROI_H           # 200*200 = 40_000 px²
    threshold_area = roi_area * OBSTACLE_AREA_THRESHOLD   # 12_000 px²

    results = model(bgr, verbose=False)[0]

    obj_debug      = bgr.copy()
    obstacle_close = False
    speed          = 40                # varsayılan hız

    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf   = float(box.conf[0])
        cls_id = int(box.cls[0])
        label  = model.names[cls_id]

        bbox_area = (x2 - x1) * (y2 - y1)
        area_pct  = bbox_area / roi_area * 100

        # Renk: yakın engel = kırmızı, uzak = sarı
        color = (0, 0, 255) if bbox_area > threshold_area else (0, 200, 255)

        cv2.rectangle(obj_debug, (x1, y1), (x2, y2), color, 2)
        cv2.putText(obj_debug,
                    f"{label} {conf:.2f} ({area_pct:.0f}%)",
                    (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)

        if bbox_area > threshold_area:
            obstacle_close = True
            speed = 0

    # Durum yazısı
    status_txt = "STOP — ENGEL YAKIN!" if obstacle_close else "GO — Yol Acik"
    status_col = (0, 0, 255)          if obstacle_close else (0, 255, 80)
    cv2.putText(obj_debug, status_txt,
                (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_col, 2)

    return obstacle_close, speed, obj_debug


# ══════════════════════════════════════════════
# SERVER
# ══════════════════════════════════════════════
def start_server() -> None:
    print("[BRAIN] YOLOv8 modeli yükleniyor...", flush=True)
    model = YOLO(MODEL_PATH)
    print(f"[BRAIN] Model hazır: {MODEL_PATH}", flush=True)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)
    print(f"[BRAIN] Listening on {HOST}:{PORT}...", flush=True)

    conn, addr = server_socket.accept()
    print(f"[BRAIN] C++ connected from {addr}", flush=True)

    pid       = PIDController(kp=0.4, ki=0.0, kd=0.05)
    frame_n   = 0
    prev_t    = time.perf_counter()
    latencies = []

    try:
        while True:
            t0 = time.perf_counter()

            # ── 1. Frame al ──────────────────────────
            raw = receive_all(conn, IMAGE_SIZE)
            if raw is None:
                print("[BRAIN] Bağlantı kesildi.", flush=True)
                break

            t1    = time.perf_counter()
            dt    = t1 - prev_t
            prev_t = t1

            rgba, bgr, gray = bytes_to_frames(raw)

            # ── 2. Şerit tespiti + PID ───────────────
            angle, lane_debug = detect_lanes(gray, pid, dt)

            # ── 3. YOLOv8 engel tespiti ──────────────
            obstacle, speed, obj_debug = detect_obstacles_yolo(bgr, model)

            # ── 4. Karar Mekanizması ─────────────────
            # Öncelik 1 → Güvenlik: engel varsa STOP
            # Öncelik 2 → Seyir: P kontrolcü ile şerit açısı
            if obstacle:
                command = "STOP\n"
                pid.reset()        # integral birikimini temizle
            else:
                command = f"{angle:.4f}\n"

            conn.sendall(command.encode("ascii"))

            # ── 5. Gecikme ölçümü ────────────────────
            t2         = time.perf_counter()
            latency_ms = (t2 - t0) * 1000
            latencies.append(latency_ms)
            frame_n   += 1

            if frame_n % 10 == 0:
                avg_lat = sum(latencies[-10:]) / 10
                fps     = 1.0 / dt if dt > 0 else 0
                print(
                    f"[FRAME {frame_n:05d}]  "
                    f"cmd={command.strip():<12}  "
                    f"angle={angle:+.2f}°  "
                    f"speed={speed}  "
                    f"lat={latency_ms:.1f}ms  "
                    f"fps={fps:.1f}",
                    flush=True
                )

            # ── 6. Debug pencereleri ─────────────────
            cv2.imshow("Detected Lanes",   lane_debug)
            cv2.imshow("Detected Objects", obj_debug)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("[BRAIN] Q basıldı, durduruluyor.", flush=True)
                break

    except Exception as e:
        print(f"[BRAIN] Hata: {e}", flush=True)
        import traceback; traceback.print_exc()

    finally:
        cv2.destroyAllWindows()
        conn.close()
        server_socket.close()
        if latencies:
            print(
                f"\n[BRAIN] Ort. gecikme: {sum(latencies)/len(latencies):.1f} ms  "
                f"({frame_n} frame)",
                flush=True
            )
        print("[BRAIN] Server kapatıldı.", flush=True)


if __name__ == "__main__":
    start_server()