import socket

def start_server():
    host = '127.0.0.1'
    port = 5000

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(1)

    print(f"Python server listening on {host}:{port}...", flush=True)

    conn, addr = server_socket.accept()
    print(f"Connected by {addr}", flush=True)

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            
            message = data.decode('utf-8').strip()
            print(f"Received from C++: {message}", flush=True)

            # Send response back
            response = "OK\n"
            conn.sendall(response.encode('utf-8'))
    except Exception as e:
        print(f"Error: {e}", flush=True)
    finally:
        conn.close()
        server_socket.close()
        print("Server closed.", flush=True)

if __name__ == "__main__":
    start_server()
