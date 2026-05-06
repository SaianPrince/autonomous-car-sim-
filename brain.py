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


def bytes_to_frames(rgba_bytes):
    arr = np.frombuffer(rgba_bytes, dtype=np.uint8)
    rgba = arr.reshape((ROI_H, ROI_W, 4))

    bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)

    return bgr, gray


def detect_lanes(gray, pid, dt):
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

    left_xs = []
    right_xs = []

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

    image_center_x = ROI_W / 2.0

    left_x = float(np.mean(left_xs)) if left_xs else None
    right_x = float(np.mean(right_xs)) if right_xs else None

    if left_x is not None and right_x is not None:
        lane_center_x = (left_x + right_x) / 2.0
    elif left_x is not None:
        lane_center_x = left_x + 50.0
    elif right_x is not None:
        lane_center_x = right_x - 50.0
    else:
        lane_center_x = image_center_x

    offset = image_center_x - lane_center_x

    angle = pid.compute(offset, dt)

    cv2.line(
        lane_debug,
        (int(lane_center_x), ROI_H // 2),
        (int(lane_center_x), ROI_H),
        (0, 255, 0),
        2
    )

    cv2.line(
        lane_debug,
        (int(image_center_x), ROI_H // 2),
        (int(image_center_x), ROI_H),
        (0, 255, 255),
        1
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
            "COMMAND: AVOID",
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

    return obstacle_detected, object_debug, red_mask, obstacle_center_x


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

    pid = PIDController(kp=0.4, ki=0.0, kd=0.05)

    frame_n = 0
    prev_t = time.perf_counter()

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

            angle, lane_debug = detect_lanes(gray, pid, dt)

            obstacle_detected, object_debug, red_mask, obstacle_center_x = detect_red_obstacle(bgr)

            if obstacle_detected:
                if obstacle_center_x is not None and obstacle_center_x < ROI_W / 2:
                    command = "25.0\n"
                else:
                    command = "-25.0\n"
            else:
                command = f"{angle:.4f}\n"

            conn.sendall(command.encode("ascii"))

            frame_n += 1

            if frame_n % 10 == 0:
                fps = 1.0 / dt if dt > 0 else 0

                print(
                    f"[FRAME {frame_n:05d}] "
                    f"command={command.strip()} "
                    f"lane_angle={angle:+.2f} "
                    f"fps={fps:.1f}",
                    flush=True
                )

            cv2.imshow("Detected Lanes", lane_debug)
            cv2.imshow("Detected Objects", object_debug)
            cv2.imshow("Red Mask", red_mask)

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