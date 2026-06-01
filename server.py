import os
import threading
import time
import re
from datetime import datetime

import docker
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from functools import wraps
from rcon.source import Client as RconClient

app = Flask(__name__, static_folder="static")

def read_env(name, fallback=""):
    """Read a value from env, with optional _FILE indirection for Docker secrets."""
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        try:
            with open(file_path) as f:
                return f.read().strip()
        except OSError as e:
            raise RuntimeError(f"Could not read secret file for {name}: {e}")
    return os.environ.get(name, fallback)

SECRET_TOKEN  = read_env("PANEL_TOKEN", "changeme")
MC_CONTAINER  = read_env("MC_CONTAINER", "mc-server")
RCON_PASSWORD = read_env("RCON_PASSWORD", "")
RCON_HOST     = read_env("RCON_HOST", "mc-server")
RCON_PORT     = int(read_env("RCON_PORT", "25575"))

restart_lock        = threading.Lock()
restart_in_progress = False
restart_log         = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_docker():
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {SECRET_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def rcon(command):
    try:
        with RconClient(RCON_HOST, RCON_PORT, passwd=RCON_PASSWORD) as client:
            return 0, client.run(command), ""
    except Exception as e:
        return -1, "", str(e)


def get_container_status():
    try:
        container = get_docker().containers.get(MC_CONTAINER)
        return container.status
    except docker.errors.NotFound:
        return "not found"
    except Exception as e:
        return f"error: {e}"


def stop_server():
    get_docker().containers.get(MC_CONTAINER).stop()


def start_server():
    get_docker().containers.get(MC_CONTAINER).start()


def get_player_count():
    try:
        code, out, err = rcon("list")
        if code != 0:
            return None, None
        match = re.search(r"There are (\d+) of a max of (\d+)", out)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, None
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Restart sequences (run in background threads)
# ---------------------------------------------------------------------------

def do_restart():
    global restart_in_progress, restart_log
    restart_log = []

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        restart_log.append(f"[{ts}] {msg}")

    try:
        log("Notifying players: restart in 5 minutes...")
        rcon("say [Panel] Server restart in 5 minutes!")
        time.sleep(180)

        log("Notifying players: restart in 2 minutes...")
        rcon("say [Panel] Server restart in 2 minutes!")
        time.sleep(60)

        log("Saving game data...")
        rcon("say [Panel] Saving game...")
        rcon("save-all flush")
        log("Save complete.")

        rcon("say [Panel] Rebooting now!")
        log("Stopping container...")
        stop_server()

        time.sleep(5)

        log("Starting container...")
        start_server()
        log("Done!")
    except Exception as e:
        log(f"Error: {e}")
    finally:
        global restart_in_progress
        restart_in_progress = False


def do_restart_now():
    global restart_in_progress, restart_log
    restart_log = []

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        restart_log.append(f"[{ts}] {msg}")

    try:
        log("Saving game data...")
        rcon("say [Panel] Emergency restart! Saving and rebooting now!")
        rcon("save-all flush")
        log("Save complete.")

        log("Stopping container...")
        stop_server()

        time.sleep(5)

        log("Starting container...")
        start_server()
        log("Done!")
    except Exception as e:
        log(f"Error: {e}")
    finally:
        global restart_in_progress
        restart_in_progress = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/resources/<path:filename>")
def resources(filename):
    return send_from_directory("static", filename)


@app.route("/api/status")
@require_token
def status():
    container_status = get_container_status()
    players, max_players = get_player_count()
    return jsonify({
        "service":             container_status,
        "players":             players,
        "max_players":         max_players,
        "restart_in_progress": restart_in_progress,
        "restart_log":         restart_log,
        "timestamp":           datetime.utcnow().isoformat() + "Z",
    })


@app.route("/api/restart", methods=["POST"])
@require_token
def restart():
    global restart_in_progress
    if restart_in_progress:
        return jsonify({"error": "Restart already in progress"}), 409
    if not restart_lock.acquire(blocking=False):
        return jsonify({"error": "Restart already in progress"}), 409
    restart_in_progress = True
    t = threading.Thread(target=do_restart, daemon=True)
    t.start()
    restart_lock.release()
    return jsonify({"ok": True, "message": "Restart sequence initiated"})


@app.route("/api/restart-now", methods=["POST"])
@require_token
def restart_now():
    global restart_in_progress
    if restart_in_progress:
        return jsonify({"error": "Restart already in progress"}), 409
    if not restart_lock.acquire(blocking=False):
        return jsonify({"error": "Restart already in progress"}), 409
    restart_in_progress = True
    t = threading.Thread(target=do_restart_now, daemon=True)
    t.start()
    restart_lock.release()
    return jsonify({"ok": True, "message": "Immediate restart initiated"})


@app.route("/api/command", methods=["POST"])
@require_token
def command():
    cmd = request.json.get("command", "").strip()
    if not cmd:
        return jsonify({"error": "No command provided"}), 400
    if any(c in cmd for c in [";", "&", "|", "`", "$", ">"]):
        return jsonify({"error": "Invalid characters in command"}), 400
    code, out, err = rcon(cmd)
    return jsonify({"output": out or err, "code": code})


@app.route("/api/logs/stream")
def logs_stream():
    # EventSource can't send headers, so accept token as query param here only
    token = request.args.get("token", "")
    if token != SECRET_TOKEN:
        return Response("data: Unauthorized\n\n", status=401, mimetype="text/event-stream")
    tail = request.args.get("tail", 100)

    def generate():
        try:
            container = get_docker().containers.get(MC_CONTAINER)
            # Stream with tail for backfill + follow for live updates
            for chunk in container.logs(
                stream=True,
                follow=True,
                timestamps=True,
                tail=int(tail)
            ):
                line = chunk.decode("utf-8", errors="replace").rstrip("\n")
                # SSE format: each message is "data: ...\n\n"
                yield f"data: {line}\n\n"
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"data: [stream error] {e}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # tells Nginx/Traefik not to buffer
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
