import time, os, socketio
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# Khởi tạo SocketIO Client
sio = socketio.Client()

def connect_to_server():
    if not sio.connected:
        try:
            sio.connect('http://127.0.0.1:5001', transports=['polling'])
            print("✅ [CONNECT] Connected to Dashboard Server")
        except Exception as e:
            # print(f"❌ [CONNECT] Failed: {e}")
            pass

class DNAHandler(FileSystemEventHandler):
    def __init__(self, watch_path):
        self.watch_path = watch_path
        self.last_triggered = {}

    def on_modified(self, event):
        if not event.is_directory:
            self.debounce_process(event.src_path, "MODIFIED")

    def on_created(self, event):
        if not event.is_directory:
            self.debounce_process(event.src_path, "CREATED")

    def debounce_process(self, filepath, event_type):
        now = time.time()
        if filepath in self.last_triggered and (now - self.last_triggered[filepath] < 2):
            return
        self.last_triggered[filepath] = now
        print(f"🔔 [EVENT] {event_type}: {os.path.basename(filepath)}")
        self.process(filepath)

    def process(self, filepath):
        filename = os.path.basename(filepath)
        if filename.startswith('.') or filename.startswith('~') or "__pycache__" in filepath:
            return

        rel_path = os.path.relpath(filepath, self.watch_path)
        parts = rel_path.split(os.sep)

        # Log để debug đường dẫn
        # print(f"DEBUG: Processing {rel_path} | Parts: {parts}")

        if len(parts) >= 2:
            # Nếu file nằm trong app/ENTITY/DOMAIN/... (không phải scripts)
            if parts[0] != 'scripts':
                if 'DNA' not in parts and filename.lower().endswith(('.csv', '.xlsx', '.xls')):
                    msg = f"New Data: {filename} in {parts[0]}"
                    self.notify(msg)
                elif 'DNA' in parts and 'Script' in parts and filename.endswith('.py'):
                    msg = f"DNA Logic updated: {filename}"
                    self.notify(msg)

    def notify(self, message):
        print(f"🚀 [NOTIFY] Attempting to send: {message}")
        connect_to_server()
        if sio.connected:
            try:
                sio.emit('dna_event', {'message': message})
                print(f"✨ [SUCCESS] Sent to UI")
            except Exception as e:
                print(f"❌ [ERROR] Send failed: {e}")
        else:
            print(f"⚠️ [OFFLINE] Server not reached. Message cached.")

if __name__ == "__main__":
    # Đảm bảo đường dẫn này trỏ đúng vào thư mục 'app' của project
    WATCH_DIR = "/home/c/AndroidStudioProjects/Cet/app"

    if not os.path.exists(WATCH_DIR):
        print(f"❌ [ERROR] Directory not found: {WATCH_DIR}")
        exit(1)

    connect_to_server()

    observer = Observer(timeout=1)
    handler = DNAHandler(WATCH_DIR)
    observer.schedule(handler, WATCH_DIR, recursive=True)

    print(f"🐕 [START] DNA Watchdog Sniffing: {WATCH_DIR}")
    observer.start()

    try:
        while True:
            time.sleep(1)
            if not sio.connected:
                connect_to_server()
    except KeyboardInterrupt:
        print("\n🛑 [STOP] Watchdog stopping...")
        observer.stop()
    observer.join()
