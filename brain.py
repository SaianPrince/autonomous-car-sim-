"""
brain.py  —  Hafta 3: Kapalı Döngü Otonom Sürüş
─────────────────────────────────────────────────
Protokol (C++ ile aynı):
  C++ → Python : 200×200 RGBA ham piksel (160_000 byte)
  Python → C++ : ASCII string  örn. "12.45\n"  (std::stof ile okunur)
"""

import socket
import struct
import time
import numpy as np
import cv2

HOST = '127.0.0.1'
PORT = 5000

ROI_W = 200
ROI_H = 200
IMAGE_SIZE = ROI_W * ROI_H * 4  # RGBA


# ══════════════════════════════════════════════
# TCP HELPER
# ══════════════════════════════════════════════
def receive_all(sock: socket.socket, size: int) -> bytes | None:
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


# ══════════════════════════════════════════════
# PID CONTROLLER (Python tarafı)
# ══════════════════════════════════════════════
class PIDController:
    """
    Hafta 3 hedefi: P dışında I ve D terimlerini de kullan.
    C++ tarafında da PID var; Python'un PID'i OFFSET'i açıya çevirir,
    C++'ın PID'i ise bu açıyı gerçek dönüş miktarına çevirir.
    """

    def __init__(self, kp: float = 0.4, ki: float = 0.0, kd: float = 0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self._prev_error  = 0.0
        self._integral    = 0.0

    def compute(self, error: float, dt: float) -> float:
        if dt <= 0:
            dt = 1e-6

        self._integral   += error * dt
        derivative        = (error - self._prev_error) / dt
        self._prev_error  = error

        output = (self.kp * error
                  + self.ki * self._integral
                  + self.kd * derivative)

        # Maksimum direksiyon açısını sınırla
        return float(np.clip(output, -30.0, 30.0))

    def reset(self):
        self._prev_error = 0.0
        self._integral   = 0.0


# ══════════════════════════════════════════════
# LANE DETECTION
# ══════════════════════════════════════════════
def detect_lanes(rgba_bytes: bytes,
                 pid: PIDController,
                 dt: float) -> tuple[float, np.ndarray]:
    """
    RGBA baytlarından şeritleri tespit eder, PID ile açı hesaplar.
    Döndürür: (angle_str, debug_image)
    """
    # 1. RGBA → Grayscale
    arr  = np.frombuffer(rgba_bytes, dtype=np.uint8)
    rgba = arr.reshape((ROI_H, ROI_W, 4))
    gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)

    # 2. Blur + Canny
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, 50, 150)

    # 3. ROI maskesi: sadece alt yarı
    mask = np.zeros_like(edges)
    mask[ROI_H // 2:, :] = 255
    masked = cv2.bitwise_and(edges, mask)

    # 4. Hough Lines
    lines = cv2.HoughLinesP(
        masked,
        rho=1,
        theta=np.pi / 180,
        threshold=20,
        minLineLength=20,
        maxLineGap=30
    )

    left_xs, right_xs = [], []
    debug = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 == x1:
                continue
            slope = (y2 - y1) / (x2 - x1)
            if abs(slope) < 0.3:   # yatay gürültüyü at
                continue
            if slope < 0:          # sol şerit
                left_xs.extend([x1, x2])
                cv2.line(debug, (x1, y1), (x2, y2), (255, 80, 0), 2)
            else:                   # sağ şerit
                right_xs.extend([x1, x2])
                cv2.line(debug, (x1, y1), (x2, y2), (0, 80, 255), 2)

    # 5. Merkez & offset
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
        lane_cx = cx            # şerit yok → düz git

    offset = cx - lane_cx       # + = sola kaydı → sağa dön

    # 6. PID → açı
    angle = pid.compute(offset, dt)

    # 7. Debug çizimler
    cv2.line(debug, (int(lane_cx), ROI_H // 2),
             (int(lane_cx), ROI_H), (0, 255, 0), 2)     # yeşil = şerit merkezi
    cv2.line(debug, (int(cx), ROI_H // 2),
             (int(cx), ROI_H), (0, 255, 255), 1)          # sarı = görüntü merkezi
    cv2.putText(debug,
                f"offset:{offset:+.1f}  angle:{angle:+.2f}",
                (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(debug,
                f"Kp={pid.kp} Ki={pid.ki} Kd={pid.kd}",
                (4, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 100), 1)

    return angle, debug


# ══════════════════════════════════════════════
# SERVER
# ══════════════════════════════════════════════
def start_server() -> None:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)
    print(f"[BRAIN] Listening on {HOST}:{PORT}...", flush=True)

    conn, addr = server_socket.accept()
    print(f"[BRAIN] C++ connected from {addr}", flush=True)

    pid = PIDController(kp=0.4, ki=0.0, kd=0.05)

    frame_n  = 0
    prev_t   = time.perf_counter()
    latencies = []

    try:
        while True:
            t0 = time.perf_counter()

            # ── 1. Frame al ───────────────────────────
            raw = receive_all(conn, IMAGE_SIZE)
            if raw is None:
                print("[BRAIN] Bağlantı kesildi.", flush=True)
                break

            t1 = time.perf_counter()
            dt = t1 - prev_t
            prev_t = t1

            # ── 2. Lane detection + PID ───────────────
            angle, debug_img = detect_lanes(raw, pid, dt)

            # ── 3. C++'a STRING olarak gönder ─────────
            # C++: angleError = std::stof(commandBuffer)
            msg = f"{angle:.4f}\n"
            conn.sendall(msg.encode('ascii'))

            t2 = time.perf_counter()
            latency_ms = (t2 - t0) * 1000
            latencies.append(latency_ms)
            frame_n += 1

            # ── 4. Terminal log (her 10 frame) ────────
            if frame_n % 10 == 0:
                avg_lat = sum(latencies[-10:]) / 10
                fps     = 1.0 / dt if dt > 0 else 0
                print(
                    f"[FRAME {frame_n:05d}] "
                    f"angle={angle:+.2f}°  "
                    f"latency={latency_ms:.1f}ms  "
                    f"fps={fps:.1f}",
                    flush=True
                )

            # ── 5. Debug penceresi ────────────────────
            cv2.imshow("Lane Detection — Hafta 3", debug_img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[BRAIN] Kullanıcı Q'ya bastı, durduruluyor.", flush=True)
                break

    except Exception as e:
        print(f"[BRAIN] Hata: {e}", flush=True)

    finally:
        cv2.destroyAllWindows()
        conn.close()
        server_socket.close()
        if latencies:
            print(
                f"\n[BRAIN] Ortalama gecikme: {sum(latencies)/len(latencies):.1f} ms  "
                f"({frame_n} frame)",
                flush=True
            )
        print("[BRAIN] Server kapatıldı.", flush=True)


if __name__ == "__main__":
    start_server()