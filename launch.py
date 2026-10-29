"""Open the existing local board, or start it when needed."""
import socket
import webbrowser

def already_running(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    if already_running():
        webbrowser.open("http://127.0.0.1:8765/")
        print("看板已在运行，已打开页面。")
    else:
        import server
        server.main()
