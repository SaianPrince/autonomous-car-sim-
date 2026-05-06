"""
test_sender.py  —  C++ Simülatörü (Mock) — Hafta 4
────────────────────────────────────────────────────
Gerçek C++ / SFML olmadan brain.py'yi test etmek için.
200x200 RGBA frame içinde:
  - Beyaz şerit çizgileri (şerit takibi testi)
  - Periyodik kırmızı engel kutusu (YOLO / STOP testi)
Protokol: doğrudan 160_000 byte RGBA → brain.py
          brain.py'den ASCII string ("12.45\n" veya "STOP\n") al
"""

import socket
import time
import numpy as np
import cv2

HOST = '127.0.0.1'
PORT = 5000

ROI_W = 200
ROI_H = 200

FRAME_DELAY = 1 / 30.0   # ~30 FPS

# Engel kaç frame göründükten sonra kaybolsun
OBSTACLE_APPEAR_EVERY  = 150   # 150 frame = 5 saniye
OBSTACLE_VISIBLE_FRAMES = 90   # 3 saniye görünür


def make_frame(frame_idx: int) -> bytes:
    """
    Normal mod: yol + şeritler
    Engel modu (periyodik): büyük kırmızı kutu eklenir
    Döndürür: RGBA bytes (160_000 byte)
    """
    img = np.zeros((ROI_H, ROI_W, 3), dtype=np.uint8)

    # ── Şerit çizgileri ──────────────────────────
    wobble  = int(8 * np.sin(frame_idx * 0.04))
    left_x  = 55 + wobble
    right_x = 145 + wobble

    # Yol zemini
    road = np.zeros((ROI_H, ROI_W), dtype=np.uint8)
    road[ROI_H // 2:, max(0, left_x):min(ROI_W, right_x)] = 35
    img[:, :, 0] = np.maximum(img[:, :, 0], road)
    img[:, :, 1] = np.maximum(img[:, :, 1], road)
    img[:, :, 2] = np.maximum(img[:, :, 2], road)

    # Şeritler
    cv2.line(img, (left_x,  ROI_H // 2), (left_x,  ROI_H), (255, 255, 255), 5)
    cv2.line(img, (right_x, ROI_H // 2), (right_x, ROI_H), (255, 255, 255), 5)

    # ── Periyodik kırmızı engel ───────────────────
    phase = frame_idx % OBSTACLE_APPEAR_EVERY
    obstacle_active = phase < OBSTACLE_VISIBLE_FRAMES

    if obstacle_active:
        # Engel boyutu zamanla büyür (yaklaşıyor efekti)
        progress  = phase / OBSTACLE_VISIBLE_FRAMES       # 0 → 1
        size      = int(30 + 90 * progress)               # 30 → 120 px
        ox        = (ROI_W - size) // 2
        oy        = max(0, int(ROI_H // 2 - size * progress))

        cv2.rectangle(img, (ox, oy), (ox + size, oy + size), (0, 0, 220), -1)
        cv2.putText(img, "ENGEL", (ox + 4, oy + size // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    # ── Kare bilgisi ─────────────────────────────
    label = f"#{frame_idx}  {'[ENGEL]' if obstacle_active else ''}"
    cv2.putText(img, label, (4, 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 200), 1)

    # BGR → RGBA
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    return rgba.tobytes()


def run() -> None:
    print(f"[MOCK C++] brain.py'ye bağlanılıyor → {HOST}:{PORT}", flush=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    for attempt in range(15):
        try:
            sock.connect((HOST, PORT))
            break
        except ConnectionRefusedError:
            print(f"[MOCK C++] Bekleniyor... ({attempt + 1}/15)", flush=True)
            time.sleep(1)
    else:
        print("[MOCK C++] HATA: brain.py'ye bağlanılamadı!", flush=True)
        return

    print("[MOCK C++] Bağlandı! Frame gönderimi başlıyor...", flush=True)
    print("[MOCK C++] Her 5 saniyede bir kırmızı engel çıkacak.", flush=True)

    frame_idx = 0
    try:
        while True:
            frame_bytes = make_frame(frame_idx)
            sock.sendall(frame_bytes)

            # brain.py'den ASCII yanıt al ("12.45\n" veya "STOP\n")
            raw = b''
            while not raw.endswith(b'\n'):
                ch = sock.recv(1)
                if not ch:
                    raise ConnectionResetError("brain.py bağlantıyı kapattı")
                raw += ch

            response = raw.decode('ascii').strip()

            if response == "STOP":
                print(f"[MOCK C++] Frame {frame_idx:05d} → 🛑 STOP!", flush=True)
            else:
                try:
                    angle = float(response)
                    if frame_idx % 15 == 0:
                        print(f"[MOCK C++] Frame {frame_idx:05d} → angle = {angle:+.2f}°", flush=True)
                except ValueError:
                    print(f"[MOCK C++] Bilinmeyen yanıt: {response!r}", flush=True)

            frame_idx += 1
            time.sleep(FRAME_DELAY)

    except (ConnectionResetError, BrokenPipeError) as e:
        print(f"[MOCK C++] Bağlantı kesildi: {e}", flush=True)
    except KeyboardInterrupt:
        print("[MOCK C++] Kullanıcı durdurdu.", flush=True)
    finally:
        sock.close()
        print("[MOCK C++] Kapatıldı.", flush=True)


if __name__ == "__main__":
    run()
