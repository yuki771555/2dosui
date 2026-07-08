"""Development-only 2dosumi API server for Android device testing."""

from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request


TOKEN = os.environ.get("TWODOSUMI_MOCK_TOKEN", "demo-token")
HOST = os.environ.get("TWODOSUMI_MOCK_HOST", "0.0.0.0")
app = Flask(__name__)
started_at = time.monotonic()
running = False

settings = {
    "reader": "mock",
    "log_path": "/tmp/2dosumi.log",
    "status_path": "/tmp/2dosumi-status.json",
    "load_cell_layout": "single",
    "zero_offset": 1000.0,
    "scale_factor": 420.0,
    "person_weight_kg": 60.0,
    "sample_interval_sec": 1.0,
    "warmup_samples": 5,
    "median_samples": 9,
    "moving_average_window": 5,
    "exit_ratio": 0.3,
    "return_ratio": 0.4,
    "monitor_sec": 1800.0,
    "confirm_sec": 180.0,
    "data_pin": "D6",
    "clock_pin": "D5",
    "hx711_ready_timeout_sec": 3.0,
    "alarm_enabled": True,
    "buzzer_enabled": True,
    "buzzer_pin": "D13",
    "buzzer_duration_sec": 5.0,
    "buzzer_pulse_sec": 0.25,
    "scheduled_alarm_enabled": True,
    "scheduled_alarms": [
        {
            "id": "weekday",
            "time": "07:00",
            "enabled": True,
            "label": "平日",
            "weekdays": [0, 1, 2, 3, 4],
        }
    ],
    "bed_recheck_minutes": 5.0,
    "wake_mission_enabled": True,
    "wake_mission_required_off_bed_sec": 30.0,
    "webhook_enabled": False,
    "webhook_events": ["second_sleep_detected"],
    "webhook_payload_format": "discord",
    "webhook_timeout_sec": 5.0,
    "webhook_url": "",
    "web_ui_token_configured": True,
    "known_events": ["second_sleep_detected", "wake_completed"],
}


@app.before_request
def authenticate():
    if request.path.startswith("/api/") and request.headers.get("X-2Dosumi-Token") != TOKEN:
        return jsonify(ok=False, error="invalid token"), 401


@app.get("/")
def index():
    return (
        "<h1>2dosumi mock Web UI</h1>"
        "<p>Android development server is running.</p>"
        f"<p>Token: <code>{TOKEN}</code></p>"
    )


@app.get("/api/settings")
def get_settings():
    return jsonify(ok=True, settings=settings)


@app.post("/api/settings")
def update_settings():
    body = request.get_json(silent=True) or {}
    settings.update(body.get("settings") or {})
    return jsonify(ok=True, running=running)


@app.get("/api/status")
def get_status():
    elapsed = time.monotonic() - started_at
    phase = int(elapsed / 12) % 3
    state, event, message = (
        ("SLEEPING", "", "在床を検知しています"),
        ("AWAKE_WINDOW", "", "離床を検知しました"),
        ("RETURNED", "second_sleep_detected", "再入床を検知しました"),
    )[phase]
    weight = max(0.0, 58.0 + math.sin(elapsed / 2) * 1.5) if phase != 1 else 2.0
    return jsonify(
        ok=True,
        status={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": 12345 if running else None,
            "running": running,
            "managed_process_running": running,
            "raw": 1000.0 + weight * 420.0,
            "weight_kg": weight,
            "smoothed_weight_kg": weight,
            "state": state if running else "",
            "event": event if running else "",
            "message": message if running else "モックセンサー待機中",
            "next_scheduled_alarm": settings["scheduled_alarms"][0],
            "pending_rechecks": [],
        },
    )


@app.post("/api/run/start")
def start_run():
    global running
    running = True
    return jsonify(ok=True, running=True)


@app.post("/api/run/stop")
def stop_run():
    global running
    running = False
    return jsonify(ok=True, running=False)


@app.post("/api/calibration/zero")
def calibrate_zero():
    settings["zero_offset"] = 1000.0
    return jsonify(ok=True, zero_offset=1000.0, restarted=running)


@app.post("/api/calibration/scale")
def calibrate_scale():
    settings["scale_factor"] = 420.0
    return jsonify(ok=True, scale_factor=420.0, restarted=running)


@app.post("/api/sensor/check")
def sensor_check():
    samples = int((request.get_json(silent=True) or {}).get("samples", 10))
    return jsonify(
        ok=True,
        restarted=running,
        sensor={
            "ok": True,
            "reader": "mock",
            "samples_requested": samples,
            "samples_read": samples,
            "raw_min": 25290.0,
            "raw_max": 25370.0,
            "raw_median": 25330.0,
            "raw_span": 80.0,
            "weight_median_kg": 58.0,
            "duration_sec": 0.2,
            "message": "モックセンサーは正常です",
            "warnings": [],
        },
    )


@app.post("/api/test-webhook")
def test_webhook():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host=HOST, port=8080, debug=False)
