import socket
import struct
import numpy as np
import cv2

HOST = '127.0.0.1'
PORT = 5000

ROI_WIDTH  = 200
ROI_HEIGHT = 200
IMAGE_SIZE = ROI_WIDTH * ROI_HEIGHT * 4  # RGBA: 4 bytes per pixel


# ──────────────────────────────────────────────
# TCP HELPER
# ──────────────────────────────────────────────
def receive_all(sock: socket.socket, size: int) -> bytes | None:
    """Guarantee we receive exactly `size` bytes."""
    data = b''
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            return None
        data += packet
    return data


# ──────────────────────────────────────────────
# LANE DETECTION
# ──────────────────────────────────────────────
def detect_lanes(rgba_bytes: bytes) -> tuple[float, np.ndarray]:
    """
    Takes raw RGBA bytes, runs lane detection, and returns:
      - angle  : steering angle (float, degrees)
      - debug  : annotated BGR image for display
    """
    # 1. RGBA → numpy array → Grayscale
    arr  = np.frombuffer(rgba_bytes, dtype=np.uint8)
    rgba = arr.reshape((ROI_HEIGHT, ROI_WIDTH, 4))
    gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)

    # 2. Blur → Canny edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, threshold1=50, threshold2=150)

    # 3. Mask: focus on the bottom half (where lanes are)
    mask = np.zeros_like(edges)
    mask[ROI_HEIGHT // 2:, :] = 255
    masked_edges = cv2.bitwise_and(edges, mask)

    # 4. Hough Line Transform
    lines = cv2.HoughLinesP(
        masked_edges,
        rho=1,
        theta=np.pi / 180,
        threshold=20,
        minLineLength=20,
        maxLineGap=30
    )

    # 5. Separate left / right lanes by slope
    left_xs  = []
    right_xs = []
    debug_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 == x1:
                continue
            slope = (y2 - y1) / (x2 - x1)

            # Skip nearly horizontal lines (noise)
            if abs(slope) < 0.3:
                continue

            # Positive slope in image coords = right lane, negative = left
            if slope < 0:
                left_xs.extend([x1, x2])
                cv2.line(debug_bgr, (x1, y1), (x2, y2), (255, 80, 0), 2)   # blue
            else:
                right_xs.extend([x1, x2])
                cv2.line(debug_bgr, (x1, y1), (x2, y2), (0, 80, 255), 2)   # red

    # 6. Compute lane centre & steering offset
    image_centre = ROI_WIDTH / 2.0
    angle = 0.0

    left_x  = np.mean(left_xs)  if left_xs  else None
    right_x = np.mean(right_xs) if right_xs else None

    if left_x is not None and right_x is not None:
        lane_centre = (left_x + right_x) / 2.0
    elif left_x is not None:
        lane_centre = left_x + 50          # estimate: lane is ~100px wide
    elif right_x is not None:
        lane_centre = right_x - 50
    else:
        lane_centre = image_centre          # no lane found → go straight

    offset = image_centre - lane_centre     # positive = drift left, steer right
    Kp     = 0.3                            # proportional gain
    angle  = float(np.clip(offset * Kp, -30.0, 30.0))

    # 7. Draw debug overlays
    cv2.line(debug_bgr,
             (int(lane_centre), ROI_HEIGHT // 2),
             (int(lane_centre), ROI_HEIGHT),
             (0, 255, 0), 2)               # green = lane centre
    cv2.line(debug_bgr,
             (int(image_centre), ROI_HEIGHT // 2),
             (int(image_centre), ROI_HEIGHT),
             (0, 255, 255), 1)             # yellow = image centre
    cv2.putText(debug_bgr,
                f"angle: {angle:.1f} deg",
                (5, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (255, 255, 255), 1)

    return angle, debug_bgr


# ──────────────────────────────────────────────
# SERVER
# ──────────────────────────────────────────────
def start_server() -> None:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)

    print(f"[BRAIN] Listening on {HOST}:{PORT}...", flush=True)

    conn, addr = server_socket.accept()
    print(f"[BRAIN] C++ connected from {addr}", flush=True)

    frame_count = 0

    try:
        while True:
            # ── Receive raw RGBA frame ─────────────────
            image_data = receive_all(conn, IMAGE_SIZE)
            if image_data is None:
                print("[BRAIN] Connection closed by C++.", flush=True)
                break

            frame_count += 1

            # ── Lane detection ─────────────────────────
            angle, debug_img = detect_lanes(image_data)

            print(f"[FRAME {frame_count:04d}] angle = {angle:+.2f} deg", flush=True)

            # ── Show debug window ──────────────────────
            cv2.imshow("Lane Detection Debug", debug_img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            # ── Send steering angle back to C++ ───────
            # Pack as 4-byte little-endian float
            conn.sendall(struct.pack('<f', angle))

    except Exception as e:
        print(f"[BRAIN] Error: {e}", flush=True)

    finally:
        cv2.destroyAllWindows()
        conn.close()
        server_socket.close()
        print("[BRAIN] Server closed.", flush=True)


if __name__ == "__main__":
    start_server()