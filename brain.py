import socket

HOST = '127.0.0.1'
PORT = 5000

IMAGE_SIZE = 200 * 200 * 4


def receive_all(sock, size):

    data = b''

    while len(data) < size:

        packet = sock.recv(size - len(data))

        if not packet:
            return None

        data += packet

    return data


def start_server():

    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server_socket.bind((HOST, PORT))

    server_socket.listen(1)

    print(
        f"Python server listening on {HOST}:{PORT}...",
        flush=True
    )

    conn, addr = server_socket.accept()

    print(f"Connected by {addr}", flush=True)

    try:

        while True:

            image_data = receive_all(
                conn,
                IMAGE_SIZE
            )

            if image_data is None:
                break

            print(
                "Received image bytes:",
                len(image_data),
                flush=True
            )

            conn.sendall(b"OK\n")

    except Exception as e:

        print(f"Error: {e}", flush=True)

    finally:

        conn.close()
        server_socket.close()

        print("Server closed.", flush=True)


if __name__ == "__main__":
    start_server()