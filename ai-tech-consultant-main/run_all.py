"""Start the API and three Streamlit apps in separate local processes."""
from __future__ import annotations
import signal
import subprocess
import sys
import time

COMMANDS = [
    [sys.executable, "-m", "uvicorn", "task1_knowledge_brain.main:app", "--host", "127.0.0.1", "--port", "8000"],
    [sys.executable, "-m", "streamlit", "run", "task1_knowledge_brain/ui.py", "--server.port", "8501", "--server.headless", "true"],
    [sys.executable, "-m", "streamlit", "run", "task2_inbox_agent/main.py", "--server.port", "8502", "--server.headless", "true"],
    [sys.executable, "-m", "streamlit", "run", "task3_meeting_scope/main.py", "--server.port", "8503", "--server.headless", "true"],
]

processes: list[subprocess.Popen] = []
def stop(*_args):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill()
    raise SystemExit(0)

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
try:
    for command in COMMANDS:
        processes.append(subprocess.Popen(command))
        time.sleep(0.5)
    print("Knowledge Brain API: http://127.0.0.1:8000/docs")
    print("Knowledge Brain UI:  http://127.0.0.1:8501")
    print("Inbox Agent UI:      http://127.0.0.1:8502")
    print("Meeting Scope UI:    http://127.0.0.1:8503")
    print("Press Ctrl+C to stop all processes.")
    while any(process.poll() is None for process in processes):
        time.sleep(1)
finally:
    stop()
