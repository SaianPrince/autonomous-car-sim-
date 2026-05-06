"""
test_sender.py  —  C++ Simülatörü (Mock)
Gerçek C++ / SFML olmadan brain.py'yi test etmek için kullanılır.
200x200 RGBA frame içinde beyaz şerit çizgileri oluşturup TCP'den gönderir.
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

FRAME_DELAY = 1 / 30.0   # ~30 FPS


def make_lane_frame(frame_idx: int) -> bytes:
    """
    200x200 siyah zemin üzerine iki beyaz dikey şerit çizer.
    frame_idx ile şeritleri hafifçe sallandırarak gerçekçilik katar.
    Döndürür: RGBA bytes (160_000 byte)
    """
    img = np.zeros((ROI_H, ROI_W, 3), dtype=np.uint8)

    # Hafif sinüsoidal titreşim — gerçekçi sürüş simülasyonu
    wobble = int(5 * np.sin(frame_idx * 0.05))

    left_x  = 60 + wobble
    right_x = 140 + wobble

    # Şerit çizgileri (beyaz, kalın)
    cv2.line(img, (left_x,  ROI_H // 2), (left_x,  ROI_H), (255, 255, 255), 5)
    cv2.line(img, (right_x, ROI_H // 2), (right_x, ROI_H), (255, 255, 255), 5)

    # Yol zemini (koyu gri)
    road_mask = np.zeros((ROI_H, ROI_W), dtype=np.uint8)
    road_mask[ROI_H // 2:, left_x:right_x] = 40
    img[:, :, 0] = np.maximum(img[:, :, 0], road_mask)
    img[:, :, 1] = np.maximum(img[:, :, 1], road_mask)
    img[:, :, 2] = np.maximum(img[:, :, 2], road_mask)

    # Kare numarasını üstüne yaz (debug)
    cv2.putText(img, f"MOCK #{frame_idx}", (5, 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 200), 1)

    # BGR → RGBA dönüşümü (C++ SFML ile aynı format)
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    return rgba.tobytes()   # 200*200*4 = 160_000 bytes


def run() -> None:
    print(f"[MOCK C++] brain.py'ye bağlanılıyor → {HOST}:{PORT}", flush=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # brain.py henüz hazır olmayabilir, birkaç kez dene
    for attempt in range(10):
        try:
            sock.connect((HOST, PORT))
            break
        except ConnectionRefusedError:
            print(f"[MOCK C++] Bekleniyor... ({attempt+1}/10)", flush=True)
            time.sleep(1)
    else:
        print("[MOCK C++] HATA: brain.py'ye bağlanılamadı!", flush=True)
        return

    print("[MOCK C++] Bağlandı! Frame gönderimi başlıyor...", flush=True)

    frame_idx = 0
    try:
        while True:
            frame_bytes = make_lane_frame(frame_idx)

            # C++ ile aynı: önce 4 byte boyut YOK — doğrudan 160_000 byte gönder
            sock.sendall(frame_bytes)

            # brain.py'den angle float'ını oku (4 byte)
            raw = b''
            while len(raw) < 4:
                chunk = sock.recv(4 - len(raw))
                if not chunk:
                    raise ConnectionResetError("brain.py bağlantıyı kapattı")
                raw += chunk

            angle = struct.unpack('<f', raw)[0]
            print(f"[MOCK C++] Frame {frame_idx:04d} → angle = {angle:+.2f}°", flush=True)

            frame_idx += 1
            time.sleep(FRAME_DELAY)

    except (ConnectionResetError, BrokenPipeError) as e:
        print(f"[MOCK C++] Bağlantı kesildi: {e}", flush=True)
    except KeyboardInterrupt:
        print("[MOCK C++] Kullanıcı durdurdu.", flush=True)
    finally:
        sock.close()


if __name__ == "__main__":
    run()
