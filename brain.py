import socket
import time
import numpy as np
import cv2

HOST = "127.0.0.1"
PORT = 5000

ROI_W = 300
ROI_H = 300
IMAGE_SIZE = ROI_W * ROI_H * 4


def receive_all(sock, size):
    data = b""

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            return None

        data += chunk

    return data


class PIDController:
    def __init__(self, kp=0.4, ki=0.0, kd=0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.previous_error = 0.0
        self.integral = 0.0

    def compute(self, error, dt):
        if dt <= 0:
            dt = 1e-6

        self.integral += error * dt
        derivative = (error - self.previous_error) / dt
        self.previous_error = error

        output = (
            self.kp * error
            + self.ki * self.integral
            + self.kd * derivative
        )

        return float(np.clip(output, -30.0, 30.0))

    def reset(self):
        self.previous_error = 0.0
        self.integral = 0.0


def bytes_to_frames(rgba_bytes):
    arr = np.frombuffer(rgba_bytes, dtype=np.uint8)
    rgba = arr.reshape((ROI_H, ROI_W, 4))

    bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)

    return bgr, gray


def detect_lanes(bgr, gray, pid, dt, target_lane):
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    mask = np.zeros_like(edges)
    mask[ROI_H // 2:, :] = 255

    masked = cv2.bitwise_and(edges, mask)

    lines = cv2.HoughLinesP(
        masked,
        rho=1,
        theta=np.pi / 180,
        threshold=20,
        minLineLength=20,
        maxLineGap=30
    )

    # 1. Heading (Eğim) Hesaplama
    heading_error = 0.0
    angles = []
    
    lane_debug = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if y1 < y2:
                x1, y1, x2, y2 = x2, y2, x1, y1
                
            dy = y1 - y2
            dx = x2 - x1
            if dy > 0:
                angle_rad = np.arctan(dx / dy)
                angles.append(angle_rad)
                cv2.line(lane_debug, (x1, y1), (x2, y2), (255, 80, 0), 2)
                
    if angles:
        heading_error = np.mean(angles) * 180.0 / np.pi
        
    # 2. Offset Hesaplama (Sarı çizgiye göre)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lower_yellow = np.array([20, 100, 100])
    upper_yellow = np.array([30, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    yellow_pixels = np.where(yellow_mask > 0)
    
    image_center_x = ROI_W / 2.0
    offset = 0.0
    
    # target_lane: 0 = Sol Şerit (Sarı çizgi 225'te olmalı)
    # target_lane: 1 = Sağ Şerit (Sarı çizgi 75'te olmalı)
    target_yellow = 225.0 if target_lane == 0 else 75.0

    if len(yellow_pixels[1]) > 0:
        yellow_x = np.mean(yellow_pixels[1])
        offset = yellow_x - target_yellow
        cv2.line(lane_debug, (int(yellow_x), ROI_H//2), (int(yellow_x), ROI_H), (0, 255, 255), 2)
    else:
        # Sarı çizgi yoksa (nadir), beyaz çizgileri kullan
        _lines = [] if lines is None else lines
        left_xs = [x1 for line in _lines for x1, y1, x2, y2 in [line[0]] if (x1+x2)/2 < image_center_x]
        right_xs = [x1 for line in _lines for x1, y1, x2, y2 in [line[0]] if (x1+x2)/2 > image_center_x]
        if left_xs:
            offset = np.mean(left_xs) - (target_yellow - 150.0)
        elif right_xs:
            offset = np.mean(right_xs) - (target_yellow + 150.0)

    # 3. PID ve Karışım
    # offset pozitifse araç fazla solda demektir -> sağa dönmeli (pozitif açı)
    steering_from_offset = pid.compute(offset, dt) 
    
    # Heading pozitifse araç sola bakıyor demektir -> sağa dönmeli (pozitif açı)
    # Yumuşak şerit takibi için katsayılar
    steering_from_heading = heading_error * 0.5
    
    angle = steering_from_offset + steering_from_heading
    angle = np.clip(angle, -30.0, 30.0)

    cv2.putText(
        lane_debug,
        f"off:{offset:+.1f} hdg:{heading_error:+.1f} ang:{angle:+.1f}",
        (4, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        2
    )

    cv2.putText(
        lane_debug,
        f"offset:{offset:+.1f} angle:{angle:+.2f}",
        (4, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1
    )

    return angle, lane_debug


def detect_red_obstacle(bgr):
    object_debug = bgr.copy()

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    lower_red_1 = np.array([0, 120, 70])
    upper_red_1 = np.array([10, 255, 255])

    lower_red_2 = np.array([170, 120, 70])
    upper_red_2 = np.array([180, 255, 255])

    mask_1 = cv2.inRange(hsv, lower_red_1, upper_red_1)
    mask_2 = cv2.inRange(hsv, lower_red_2, upper_red_2)

    red_mask = mask_1 + mask_2

    contours, _ = cv2.findContours(
        red_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    obstacle_detected = False
    obstacle_center_x = None

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < 1200:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        obstacle_detected = True
        obstacle_center_x = x + w / 2.0

        cv2.rectangle(
            object_debug,
            (x, y),
            (x + w, y + h),
            (0, 255, 0),
            2
        )

        cv2.putText(
            object_debug,
            "RED OBSTACLE",
            (x, max(15, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1
        )

    if obstacle_detected:
        cv2.putText(
            object_debug,
            "COMMAND: LANE CHANGE",
            (4, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            2
        )
    else:
        cv2.putText(
            object_debug,
            "NO OBSTACLE",
            (4, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1
        )

    return obstacle_detected, object_debug, obstacle_center_x



def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_socket.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server_socket.bind((HOST, PORT))
    server_socket.listen(1)

    print(f"[BRAIN] Listening on {HOST}:{PORT}...", flush=True)

    conn, addr = server_socket.accept()

    print(f"[BRAIN] C++ connected from {addr}", flush=True)

    # Şerit takibi için yumuşak PID (Manevra artık matematiksel)
    pid = PIDController(kp=0.05, ki=0.0, kd=0.02)

    frame_n = 0
    prev_t = time.perf_counter()

    # ── Kaçınma durum makinesi ─────────────────────
    # STATE 0: Normal
    # STATE 1: DODGE1 (şerit değiştir)
    # STATE 2: DODGE2 (aracı düzelt)
    # STATE 3: PASS (yan şeritte ilerle)
    # STATE 4: RETURN1 (kendi şeridine dön)
    # STATE 5: RETURN2 (aracı düzelt)
    
    cooldown_time = 0.0
    target_lane   = 0  # 0: Sol şerit, 1: Sağ şerit
    maneuver_state = 0
    maneuver_timer = 0.0
    dodge_dir = 0
    pid.reset()

    try:
        while True:
            raw = receive_all(conn, IMAGE_SIZE)

            if raw is None:
                print("[BRAIN] Connection closed.", flush=True)
                break

            now = time.perf_counter()
            dt = now - prev_t
            prev_t = now

            bgr, gray = bytes_to_frames(raw)

            # Geçerli şeridi algıla (cooldown yokken)
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            lower_yellow = np.array([20, 100, 100])
            upper_yellow = np.array([30, 255, 255])
            yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
            yellow_pixels = np.where(yellow_mask > 0)
            
            if cooldown_time <= 0 and len(yellow_pixels[1]) > 0:
                yellow_x = np.mean(yellow_pixels[1])
                target_lane = 0 if yellow_x > ROI_W / 2 else 1

            lane_angle, lane_debug = detect_lanes(bgr, gray, pid, dt, target_lane)
            obstacle_detected, object_debug, obstacle_cx = detect_red_obstacle(bgr)

            cooldown_time -= dt

            if cooldown_time <= 0 and obstacle_detected:
                dangerous_obstacle = False
                dodge_dir = 0
                
                if len(yellow_pixels[1]) > 0:
                    yellow_x = np.mean(yellow_pixels[1])
                    if target_lane == 0:
                        # Sol şeritteyiz, engel sarı çizginin solundaysa tehlike!
                        if obstacle_cx < yellow_x + 10:
                            dangerous_obstacle = True
                            dodge_dir = 1
                    else:
                        # Sağ şeritteyiz, engel sarı çizginin sağındaysa tehlike!
                        if obstacle_cx > yellow_x - 10:
                            dangerous_obstacle = True
                            dodge_dir = -1
                
                if dangerous_obstacle:
                    target_lane = 1 - target_lane  # Şerit değiştir!
                    maneuver_state = 1
                    maneuver_timer = 1.16  # Tam 1.16 saniye (Matematiksel 150 piksel hesabı)
                    cooldown_time = 3.0  # 3 saniye boyunca yeni karar alma
                    pid.reset()
                    print(f"[BRAIN] TEHLIKELI ENGEL! Matematiksel manevra basladi: {'SAG' if target_lane == 1 else 'SOL'}", flush=True)

            # Matematiksel Manevra Yürütme (Açık Döngü)
            if maneuver_state == 1:
                # Dışarı kır (Örn: Sağa geçiş için +30)
                command_angle = dodge_dir * 30.0
                maneuver_timer -= dt
                if maneuver_timer <= 0:
                    maneuver_state = 2
                    maneuver_timer = 1.16  # İkinci yarı: 1.16 saniye
            elif maneuver_state == 2:
                # İçeri topla (Örn: Sağa geçişte düzelmek için -30)
                command_angle = -dodge_dir * 30.0
                maneuver_timer -= dt
                if maneuver_timer <= 0:
                    maneuver_state = 0  # Manevra bitti, PID devralsın
            else:
                # Normal şerit takibi
                command_angle = lane_angle

            command = f"{command_angle:.4f}\n"
            conn.sendall(command.encode("ascii"))

            frame_n += 1
            if frame_n % 10 == 0:
                fps = 1.0 / dt if dt > 0 else 0
                lane_name = "SOL" if target_lane == 0 else "SAG"
                print(
                    f"[HEDEF: {lane_name}][FRAME {frame_n:05d}]  "
                    f"angle={lane_angle:+.2f}°  "
                    f"fps={fps:.1f}",
                    flush=True
                )

            cv2.imshow("Detected Lanes", lane_debug)
            cv2.imshow("Detected Objects", object_debug)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("[BRAIN] Q pressed. Stopping.", flush=True)
                break

    except Exception as e:
        print(f"[BRAIN] Error: {e}", flush=True)

    finally:
        cv2.destroyAllWindows()
        conn.close()
        server_socket.close()
        print("[BRAIN] Server closed.", flush=True)


if __name__ == "__main__":
    start_server()