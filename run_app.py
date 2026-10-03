import os
import subprocess
import sys
import time
import urllib.request
import webbrowser


ROOT = os.path.dirname(os.path.abspath(__file__))
URLS = ("http://127.0.0.1:5000/", "http://127.0.0.1:5000/admin/login")


def wait_for_server(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.25)
    return False


def main():
    process = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT)
    try:
        if not wait_for_server(URLS[0]):
            raise RuntimeError("Flask did not start within 30 seconds.")
        for url in URLS:
            webbrowser.open_new_tab(url)
        print("Opened the home page and admin login page. Press Ctrl+C to stop Flask.")
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
