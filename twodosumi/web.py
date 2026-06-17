from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from .cli import calibrate_scale_file, calibrate_zero_file
from .config import (
    AppConfig,
    KNOWN_EVENTS,
    ScheduledAlarmConfig,
    Secrets,
    load_config,
    load_secrets,
    save_config,
    save_secrets,
    validate_config,
)
from .notifier import send_test_webhook
from .sensors import check_sensor
from .status import read_status


EDITABLE_CONFIG_FIELDS = {
    "log_path",
    "status_path",
    "person_weight_kg",
    "sample_interval_sec",
    "warmup_samples",
    "median_samples",
    "moving_average_window",
    "exit_ratio",
    "return_ratio",
    "monitor_sec",
    "confirm_sec",
    "data_pin",
    "clock_pin",
    "hx711_ready_timeout_sec",
    "alarm_enabled",
    "buzzer_enabled",
    "buzzer_pin",
    "buzzer_duration_sec",
    "buzzer_pulse_sec",
    "scheduled_alarm_enabled",
    "scheduled_alarms",
    "bed_recheck_minutes",
    "webhook_enabled",
    "webhook_events",
    "webhook_payload_format",
    "webhook_timeout_sec",
}


class ProcessManager:
    def __init__(self, config_path: str, secrets_path: str) -> None:
        self.config_path = config_path
        self.secrets_path = secrets_path
        self.process: subprocess.Popen[bytes] | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        command = [
            sys.executable,
            "-m",
            "twodosumi",
            "run",
            "--config",
            self.config_path,
            "--secrets",
            self.secrets_path,
        ]
        self.process = subprocess.Popen(command)

    def stop(self) -> None:
        if not self.is_running():
            self.process = None
            return
        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.process = None


def _coerce_config_value(field: str, value: Any) -> Any:
    int_fields = {"warmup_samples", "median_samples", "moving_average_window"}
    float_fields = {
        "person_weight_kg",
        "sample_interval_sec",
        "exit_ratio",
        "return_ratio",
        "monitor_sec",
        "confirm_sec",
        "hx711_ready_timeout_sec",
        "buzzer_duration_sec",
        "buzzer_pulse_sec",
        "bed_recheck_minutes",
        "webhook_timeout_sec",
    }
    bool_fields = {"alarm_enabled", "buzzer_enabled", "scheduled_alarm_enabled", "webhook_enabled"}
    list_fields = {"webhook_events"}

    if field in int_fields:
        return int(value)
    if field in float_fields:
        return float(value)
    if field in bool_fields:
        return bool(value)
    if field in list_fields:
        if not isinstance(value, list):
            raise ValueError(f"{field} must be a list")
        return [str(item) for item in value]
    if field == "scheduled_alarms":
        if not isinstance(value, list):
            raise ValueError("scheduled_alarms must be a list")
        return [
            ScheduledAlarmConfig(
                id=str(item.get("id", "")),
                time=str(item.get("time", "07:00")),
                enabled=bool(item.get("enabled", True)),
                label=str(item.get("label", "")),
                weekdays=[int(day) for day in item.get("weekdays", [0, 1, 2, 3, 4, 5, 6])],
            )
            for item in value
            if isinstance(item, dict)
        ]
    return str(value)


def create_app(config_path: str, secrets_path: str):
    try:
        from flask import Flask, jsonify, request
    except ImportError as exc:
        raise RuntimeError("Install Flask first: python3 -m pip install -r requirements-pi.txt") from exc

    app = Flask(__name__)
    manager = ProcessManager(config_path, secrets_path)

    def error_response(message: str, status: int = 400):
        return jsonify({"ok": False, "error": message}), status

    def require_auth(handler: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            secrets = load_secrets(secrets_path)
            if not secrets.web_ui_token:
                return error_response("web_ui_token is not configured", 503)
            token = request.headers.get("X-2Dosumi-Token", "")
            if token != secrets.web_ui_token:
                return error_response("unauthorized", 401)
            return handler(*args, **kwargs)

        wrapped.__name__ = handler.__name__
        return wrapped

    @app.get("/")
    def index() -> str:
        return INDEX_HTML

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.get("/api/settings")
    @require_auth
    def get_settings():
        config = load_config(config_path)
        secrets = load_secrets(secrets_path)
        data = asdict(config)
        data["webhook_url"] = secrets.webhook_url
        data["web_ui_token_configured"] = bool(secrets.web_ui_token)
        data["known_events"] = sorted(KNOWN_EVENTS)
        return jsonify({"ok": True, "settings": data})

    @app.post("/api/settings")
    @require_auth
    def post_settings():
        payload = request.get_json(force=True, silent=True) or {}
        settings = payload.get("settings", payload)
        if not isinstance(settings, dict):
            return error_response("settings must be an object")

        config = load_config(config_path)
        secrets = load_secrets(secrets_path)
        for field, value in settings.items():
            if field in EDITABLE_CONFIG_FIELDS:
                setattr(config, field, _coerce_config_value(field, value))
            elif field == "webhook_url":
                secrets.webhook_url = str(value)
            elif field == "web_ui_token" and value:
                secrets.web_ui_token = str(value)

        errors = validate_config(config)
        if errors:
            return error_response("; ".join(errors))
        save_config(config_path, config)
        save_secrets(secrets_path, secrets)
        return jsonify({"ok": True})

    @app.get("/api/status")
    @require_auth
    def get_status():
        config = load_config(config_path)
        status = read_status(config.status_path)
        status["managed_process_running"] = manager.is_running()
        return jsonify({"ok": True, "status": status})

    @app.post("/api/run/start")
    @require_auth
    def start_run():
        manager.start()
        return jsonify({"ok": True, "running": manager.is_running()})

    @app.post("/api/run/stop")
    @require_auth
    def stop_run():
        manager.stop()
        return jsonify({"ok": True, "running": manager.is_running()})

    @app.post("/api/calibration/zero")
    @require_auth
    def calibrate_zero():
        was_running = manager.is_running()
        if was_running:
            manager.stop()
        try:
            payload = request.get_json(force=True, silent=True) or {}
            samples = int(payload.get("samples", 30))
            zero = calibrate_zero_file(config_path, samples)
        finally:
            if was_running:
                manager.start()
        return jsonify({"ok": True, "zero_offset": zero, "restarted": was_running})

    @app.post("/api/calibration/scale")
    @require_auth
    def calibrate_scale():
        was_running = manager.is_running()
        if was_running:
            manager.stop()
        try:
            payload = request.get_json(force=True, silent=True) or {}
            samples = int(payload.get("samples", 30))
            known_kg = float(payload.get("known_kg", 0))
            scale = calibrate_scale_file(config_path, known_kg, samples)
        finally:
            if was_running:
                manager.start()
        return jsonify({"ok": True, "scale_factor": scale, "restarted": was_running})

    @app.post("/api/sensor/check")
    @require_auth
    def sensor_check():
        was_running = manager.is_running()
        if was_running:
            manager.stop()
        try:
            payload = request.get_json(force=True, silent=True) or {}
            samples = int(payload.get("samples", 10))
            interval_sec = float(payload.get("interval_sec", 0.1))
            config = load_config(config_path)
            errors = validate_config(config)
            if errors:
                return error_response("; ".join(errors))
            result = check_sensor(config, samples=samples, interval_sec=interval_sec)
        finally:
            if was_running:
                manager.start()
        return jsonify({"ok": True, "sensor": asdict(result), "restarted": was_running})

    @app.post("/api/test-webhook")
    @require_auth
    def test_webhook():
        config = load_config(config_path)
        secrets = load_secrets(secrets_path)
        if not secrets.webhook_url:
            return error_response("webhook_url is not configured")
        send_test_webhook(config, secrets)
        return jsonify({"ok": True})

    return app


def ensure_secrets_file(path: str) -> None:
    target = Path(path)
    if target.exists():
        return
    token = os.urandom(12).hex()
    save_secrets(target, Secrets(web_ui_token=token))
    print(f"Created {target} with web_ui_token={token}", flush=True)


def run_web(config_path: str, secrets_path: str, host: str, port: int) -> None:
    ensure_secrets_file(secrets_path)
    app = create_app(config_path, secrets_path)
    print(f"Open http://{host}:{port}", flush=True)
    app.run(host=host, port=port)


INDEX_HTML = r"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>2dosumi</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --bg: #f2f2f7;
      --panel: #ffffff;
      --panel-soft: #f8f8fb;
      --ink: #111114;
      --muted: #6c6c70;
      --line: #d8d8df;
      --accent: #ff9500;
      --accent-dark: #c76500;
      --accent-soft: #fff2df;
      --good: #34c759;
      --warn: #ff3b30;
      --blue: #007aff;
      --shadow: 0 18px 48px rgba(22, 22, 28, 0.12);
      --button-shadow: 0 10px 20px rgba(255, 149, 0, 0.24);
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      min-height: 100vh;
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }
    main { width: min(100%, 1180px); margin: 0 auto; padding: 18px; }
    h1, h2 { margin: 0; letter-spacing: 0; }
    h1 { font-size: clamp(30px, 5vw, 48px); line-height: 0.98; }
    h2 { font-size: 16px; }
    p { margin: 0; }
    a, button, input, select, strong, span { min-width: 0; }
    .app-frame {
      position: relative;
      overflow: clip;
      border: 1px solid rgba(216, 216, 223, 0.88);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.76);
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }
    .app-frame::before { content: none; }
    .app-bar {
      position: relative;
      z-index: 1;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      min-height: 64px;
      padding: 0 20px;
      border-bottom: 1px solid rgba(216, 216, 223, 0.76);
      background: rgba(255, 255, 255, 0.82);
      backdrop-filter: blur(18px);
    }
    .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      background: linear-gradient(135deg, var(--accent), #ffcc00);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.48), 0 10px 20px rgba(255, 149, 0, 0.2);
    }
    .brand-text { display: grid; gap: 2px; min-width: 0; }
    .brand strong { font-size: 17px; font-weight: 900; }
    .brand span { color: var(--muted); font-size: 12px; font-weight: 750; }
    .content { position: relative; z-index: 1; padding: 12px; }
    .quick-tabs {
      position: sticky;
      top: 0;
      z-index: 4;
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      padding: 8px;
      margin-bottom: 10px;
      border: 1px solid rgba(216, 216, 223, 0.78);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.84);
      backdrop-filter: blur(16px);
    }
    .quick-tabs a {
      display: grid;
      place-items: center;
      min-height: 34px;
      border-radius: 7px;
      color: var(--ink);
      text-decoration: none;
      font-size: 13px;
      font-weight: 850;
    }
    .quick-tabs a:hover { background: var(--panel-soft); }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.18fr) minmax(min(100%, 280px), 0.82fr);
      gap: 12px;
      min-height: 210px;
      overflow: hidden;
      border: 1px solid rgba(216, 216, 223, 0.96);
      border-radius: 8px;
      background: linear-gradient(135deg, #ffffff, #fff7ed 64%, #eef7ff);
      box-shadow: 0 10px 26px rgba(22, 22, 28, 0.08);
    }
    .hero-copy { display: flex; flex-direction: column; justify-content: space-between; gap: 22px; padding: 26px; }
    .hero-title { display: grid; gap: 13px; }
    .hero-kicker {
      width: fit-content;
      padding: 5px 9px;
      border: 1px solid rgba(255, 149, 0, 0.28);
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-dark);
      font-size: 12px;
      font-weight: 850;
    }
    .hero-sub { max-width: 44rem; color: var(--muted); font-size: 15px; line-height: 1.68; }
    .hero-panel { display: grid; align-content: stretch; padding: 14px; }
    .live-card {
      display: grid;
      align-content: space-between;
      min-height: 100%;
      padding: 20px;
      border: 1px solid rgba(216, 216, 223, 0.92);
      border-radius: 8px;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(247, 251, 252, 0.76)),
        var(--panel);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
    }
    .live-card span { color: var(--muted); font-size: 12px; font-weight: 850; }
    .live-card strong { display: block; margin-top: 8px; font-size: 32px; line-height: 1; overflow-wrap: anywhere; }
    .alarm-card {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      padding: 15px;
      border: 1px solid rgba(216, 216, 223, 0.92);
      border-radius: 8px;
      background: #fff;
    }
    .alarm-card strong { display: block; font-size: 15px; }
    .alarm-card span { display: block; margin-top: 3px; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .alarm-preview-list { display: grid; gap: 8px; margin-top: 10px; }
    .alarm-preview-item {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .alarm-preview-time { font-size: 22px; font-weight: 900; white-space: nowrap; }
    .alarm-preview-meta { display: grid; gap: 2px; min-width: 0; }
    .alarm-preview-meta strong { overflow-wrap: anywhere; }
    .alarm-preview-meta span { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .link-button {
      display: grid;
      place-items: center;
      min-height: 44px;
      margin-top: 10px;
      border-radius: 7px;
      background: var(--panel-soft);
      color: var(--blue);
      font-weight: 850;
      text-decoration: none;
    }
    .link-button:hover { background: #eef5ff; }
    .switch {
      position: relative;
      display: inline-flex;
      width: 58px;
      min-width: 58px;
      height: 34px;
    }
    .switch input { position: absolute; inset: 0; z-index: 2; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
    .slider {
      position: absolute;
      inset: 0;
      border-radius: 999px;
      background: #c7d2d8;
      transition: background 160ms ease;
      cursor: pointer;
    }
    .slider::after {
      content: "";
      position: absolute;
      width: 28px;
      height: 28px;
      top: 3px;
      left: 3px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 3px 10px rgba(25, 42, 54, 0.2);
      transition: transform 160ms ease;
    }
    .switch input:checked + .slider { background: var(--good); }
    .switch input:checked + .slider::after { transform: translateX(24px); }
    .top-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 10px; align-items: center; }
    .shell { display: grid; grid-template-columns: minmax(280px, 0.82fr) minmax(0, 1.18fr); gap: 12px; margin-top: 12px; }
    section {
      background: rgba(255, 255, 255, 0.93);
      border: 1px solid rgba(216, 216, 223, 0.86);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 10px 24px rgba(22, 22, 28, 0.06);
    }
    section, .setting-group, .alarm-card, .metric, .live-card { min-width: 0; }
    section { scroll-margin-top: 82px; }
    .stack { display: grid; gap: 14px; align-content: start; }
    .section-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 14px; }
    .section-head.sticky {
      position: sticky;
      top: 61px;
      z-index: 3;
      margin: -16px -16px 14px;
      padding: 14px 16px;
      border-bottom: 1px solid rgba(216, 216, 223, 0.76);
      background: rgba(255, 255, 255, 0.92);
      backdrop-filter: blur(16px);
    }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 184px), 1fr)); gap: 12px; }
    .settings-grid { grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); }
    .setting-group {
      display: grid;
      gap: 12px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .setting-group.wide { grid-column: 1 / -1; }
    .setting-group h3 {
      margin: 0;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(216, 216, 223, 0.82);
      font-size: 15px;
      letter-spacing: 0;
    }
    .setting-group-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 12px; }
    .scheduled-editor { display: grid; gap: 12px; grid-column: 1 / -1; }
    .scheduled-row {
      display: grid;
      grid-template-columns: minmax(170px, 0.8fr) minmax(220px, 1.2fr) minmax(88px, auto);
      gap: 12px;
      align-items: center;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .scheduled-time-block { display: flex; align-items: center; gap: 13px; min-width: 0; flex-wrap: wrap; }
    .scheduled-time-block .scheduled-time {
      min-height: 54px;
      padding: 6px 8px;
      border: 0;
      background: transparent;
      color: var(--ink);
      width: 132px;
      font-size: 28px;
      font-weight: 850;
    }
    .scheduled-detail { display: grid; gap: 9px; min-width: 0; }
    .scheduled-detail .scheduled-label {
      min-height: 38px;
      border-radius: 8px;
      background: var(--panel-soft);
    }
    .weekday-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-width: 0; }
    .weekday-row label {
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      min-height: 34px;
      padding: 4px 9px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel-soft);
      color: var(--ink);
      font-size: 12px;
      font-weight: 800;
    }
    .weekday-row input {
      position: absolute;
      width: 1px;
      min-height: 1px;
      opacity: 0;
      pointer-events: none;
    }
    .weekday-row label:has(input) { cursor: pointer; }
    .weekday-row label:has(input:checked) {
      border-color: rgba(52, 199, 89, 0.32);
      background: #eaf8ef;
      color: #188a3d;
    }
    label { display: grid; gap: 6px; font-size: 12px; color: var(--muted); font-weight: 650; min-width: 0; }
    input, select {
      width: 100%;
      min-height: 44px;
      font: inherit;
      padding: 9px 10px;
      border: 1px solid #d1d1d6;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.92);
      color: var(--ink);
      outline: none;
    }
    input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(255, 149, 0, 0.16); }
    input[type="checkbox"] { width: 20px; min-height: 20px; accent-color: var(--good); }
    input[type="time"] { min-width: 0; }
    button {
      min-height: 44px;
      font: inherit;
      font-weight: 750;
      padding: 9px 13px;
      border: 0;
      border-radius: 6px;
      background: linear-gradient(180deg, #ffa724, var(--accent));
      color: white;
      cursor: pointer;
      box-shadow: var(--button-shadow);
      transition: transform 140ms ease, box-shadow 140ms ease, background 140ms ease;
    }
    button:hover { transform: translateY(-1px); box-shadow: 0 12px 22px rgba(255, 149, 0, 0.26); }
    button:active { transform: translateY(0); box-shadow: var(--button-shadow); }
    button.secondary { background: linear-gradient(180deg, #178cff, var(--blue)); box-shadow: 0 10px 18px rgba(0, 122, 255, 0.18); }
    button.secondary:hover { background: linear-gradient(180deg, #0b80f5, #006edc); box-shadow: 0 12px 22px rgba(0, 122, 255, 0.22); }
    button.warn { background: linear-gradient(180deg, #ff5b52, var(--warn)); box-shadow: 0 10px 18px rgba(255, 59, 48, 0.18); }
    button.warn:hover { background: linear-gradient(180deg, #f84d45, #e22e25); box-shadow: 0 12px 22px rgba(255, 59, 48, 0.22); }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; min-width: 0; }
    .actions button { flex: 1 1 150px; }
    .status-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: 10px; margin-bottom: 12px; }
    .metric {
      position: relative;
      overflow: hidden;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px;
      min-height: 78px;
    }
    .metric::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--blue));
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; font-weight: 700; }
    .metric strong { display: block; margin-top: 5px; font-size: 20px; overflow-wrap: anywhere; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 11px;
      border: 1px solid rgba(26, 117, 91, 0.18);
      border-radius: 999px;
      font-size: 12px;
      font-weight: 850;
      background: #eaf8ef;
      color: var(--good);
      white-space: nowrap;
    }
    .pill.off { border-color: rgba(255, 59, 48, 0.18); background: #fff0ef; color: var(--warn); }
    .status {
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 12px;
      line-height: 1.55;
      margin: 0;
      padding: 12px;
      border-radius: 8px;
      background: #111a22;
      color: #e7f0f5;
    }
    .sensor-check-result {
      display: grid;
      gap: 8px;
      margin-top: 12px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-soft);
      color: var(--ink);
      font-size: 13px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .sensor-check-result.ok { border-color: rgba(52, 199, 89, 0.28); background: #f3fbf5; }
    .sensor-check-result.fail { border-color: rgba(255, 59, 48, 0.28); background: #fff5f4; }
    .message {
      position: sticky;
      bottom: 12px;
      z-index: 2;
      min-height: 28px;
      margin: 14px 0 0;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(23, 33, 43, 0.92);
      color: white;
      font-weight: 750;
      opacity: 0;
      transition: opacity 160ms ease;
    }
    .message.show { opacity: 1; }
    .full { grid-column: 1 / -1; }
    @media (max-width: 980px) {
      .shell { grid-template-columns: 1fr; }
      .scheduled-row { grid-template-columns: minmax(0, 1fr); align-items: stretch; }
      .scheduled-row .warn { width: 100%; }
    }
    @media (max-width: 820px) {
      main { padding: 10px; }
      .content { padding: 10px; }
      .app-bar { min-height: 54px; padding: 0 12px; }
      .brand-text span { display: none; }
      .brand-mark { width: 30px; height: 30px; }
      .hero { grid-template-columns: 1fr; min-height: 0; }
      .hero-copy { padding: 20px; }
      .hero-panel { padding: 0 20px 20px; }
      .live-card { min-height: 122px; }
      .top-actions { grid-template-columns: 1fr 1fr; }
      .top-actions .secondary { grid-column: 1 / -1; }
      button { flex: 1 1 132px; }
      .alarm-card { align-items: flex-start; }
      .section-head.sticky { top: 55px; }
    }
    @media (max-width: 520px) {
      main { padding: 0; }
      .app-frame { border-radius: 0; border-left: 0; border-right: 0; }
      .quick-tabs { grid-template-columns: repeat(2, 1fr); }
      .hero-copy { padding: 18px; }
      .hero-panel { padding: 0 18px 18px; }
      .top-actions { grid-template-columns: 1fr; }
      .section-head, .alarm-card { align-items: stretch; flex-direction: column; }
      .section-head.sticky .actions { width: 100%; }
      .scheduled-time-block { justify-content: space-between; }
      .scheduled-time-block .scheduled-time { flex: 1; font-size: 26px; }
      .status { max-height: 190px; }
    }
  </style>
</head>
<body>
<main>
  <div class="app-frame">
    <div class="app-bar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <span class="brand-text"><strong>2dosumi</strong><span>Bed sensor control</span></span>
      </div>
      <span id="run-pill" class="pill off">停止中</span>
    </div>
    <div class="content">
      <nav class="quick-tabs" aria-label="画面移動">
        <a href="#alarms">アラーム</a>
        <a href="#status-panel">状態</a>
        <a href="#settings-panel">設定</a>
        <a href="#calibration-panel">校正</a>
      </nav>
      <header class="hero">
        <div class="hero-copy">
          <div class="hero-title">
            <p class="hero-kicker">Raspberry Pi sleep monitor</p>
            <h1>2dosumi</h1>
            <p class="hero-sub">ベッド荷重の状態、通知、校正をひとつの画面で管理します。</p>
          </div>
          <div class="top-actions">
            <button onclick="post('/api/run/start')">開始</button>
            <button class="warn" onclick="post('/api/run/stop')">停止</button>
            <button class="secondary" onclick="loadStatus()">更新</button>
          </div>
        </div>
        <div class="hero-panel">
          <div class="live-card">
            <div>
              <span>現在の状態</span>
              <strong id="hero-state">-</strong>
            </div>
            <div>
              <span>平滑重量</span>
              <strong id="hero-weight">-</strong>
            </div>
          </div>
        </div>
      </header>

      <div class="shell">
        <div class="stack" id="alarms">
          <section>
            <div class="section-head"><h2>時刻アラーム</h2><span id="scheduled-alarm-pill" class="pill off">OFF</span></div>
            <div class="alarm-card">
              <div>
                <strong>複数アラーム</strong>
                <span id="scheduled-alarm-next">次のアラームは未設定です。</span>
              </div>
              <label class="switch" aria-label="時刻アラーム">
                <input id="quick_scheduled_alarm_enabled" type="checkbox" onchange="toggleScheduledAlarm(this.checked)">
                <span class="slider"></span>
              </label>
            </div>
            <div id="alarm-preview-list" class="alarm-preview-list"></div>
            <a class="link-button" href="#settings-panel">アラームを編集</a>
          </section>

          <section>
            <div class="section-head"><h2>二度寝検知アラーム</h2><span id="alarm-pill" class="pill off">OFF</span></div>
            <div class="alarm-card">
              <div>
                <strong>アラーム</strong>
                <span>ONにすると2度寝検知時にDiscord通知とブザーを鳴らします。</span>
              </div>
              <label class="switch" aria-label="2度寝アラーム">
                <input id="quick_alarm_enabled" type="checkbox" onchange="toggleAlarm(this.checked)">
                <span class="slider"></span>
              </label>
            </div>
          </section>

          <section>
            <div class="section-head"><h2>認証</h2></div>
            <div class="grid">
              <label>Web UI Token<input id="token" type="password" autocomplete="current-password"></label>
            </div>
            <div class="actions">
              <button onclick="saveToken()">保存</button>
              <button class="secondary" onclick="loadSettings()">読み込み</button>
            </div>
          </section>

          <section id="calibration-panel">
            <div class="section-head"><h2>キャリブレーション</h2></div>
            <div class="grid">
              <label>samples<input id="cal_samples" type="number" value="30" min="1"></label>
              <label>known kg<input id="known_kg" type="number" step="0.1" min="0"></label>
            </div>
            <div class="actions">
              <button class="secondary" onclick="checkSensor()">センサー確認</button>
              <button onclick="calibrateZero()">ゼロ校正</button>
              <button onclick="calibrateScale()">重量校正</button>
            </div>
            <div id="sensor-check-result" class="sensor-check-result">未確認</div>
          </section>
        </div>

        <section id="status-panel">
          <div class="section-head">
            <h2>状態</h2>
            <span id="status-time" class="pill off">未取得</span>
          </div>
          <div class="status-cards">
            <div class="metric"><span>state</span><strong id="metric-state">-</strong></div>
            <div class="metric"><span>event</span><strong id="metric-event">-</strong></div>
            <div class="metric"><span>weight</span><strong id="metric-weight">-</strong></div>
            <div class="metric"><span>process</span><strong id="metric-process">-</strong></div>
            <div class="metric"><span>next alarm</span><strong id="metric-next-alarm">-</strong></div>
            <div class="metric"><span>recheck</span><strong id="metric-recheck">-</strong></div>
          </div>
          <pre id="status" class="status">未取得</pre>
        </section>

        <section class="full" id="settings-panel">
          <div class="section-head sticky">
            <h2>設定</h2>
            <div class="actions">
              <button onclick="saveSettings()">設定を保存</button>
              <button class="secondary" onclick="post('/api/test-webhook')">Webhookテスト</button>
            </div>
          </div>
          <div id="settings" class="grid settings-grid"></div>
        </section>
      </div>
    </div>
  </div>
  <p id="message" class="message"></p>
</main>
<script>
const fields = [
  ['log_path','text'], ['status_path','text'], ['person_weight_kg','number'],
  ['sample_interval_sec','number'], ['warmup_samples','number'], ['median_samples','number'],
  ['moving_average_window','number'], ['exit_ratio','number'], ['return_ratio','number'],
  ['monitor_sec','number'], ['confirm_sec','number'], ['data_pin','text'], ['clock_pin','text'],
  ['hx711_ready_timeout_sec','number'], ['alarm_enabled','checkbox'], ['buzzer_enabled','checkbox'],
  ['buzzer_pin','text'], ['buzzer_duration_sec','number'], ['buzzer_pulse_sec','number'],
  ['scheduled_alarm_enabled','checkbox'], ['bed_recheck_minutes','number'],
  ['webhook_enabled','checkbox'], ['webhook_events','text'],
  ['webhook_payload_format','select'], ['webhook_timeout_sec','number'], ['webhook_url','password']
];
const fieldGroups = [
  ['基本', ['person_weight_kg', 'sample_interval_sec', 'log_path', 'status_path']],
  ['検知', ['exit_ratio', 'return_ratio', 'monitor_sec', 'confirm_sec', 'moving_average_window']],
  ['センサー', ['warmup_samples', 'median_samples', 'data_pin', 'clock_pin', 'hx711_ready_timeout_sec']],
  ['時刻アラーム', ['scheduled_alarm_enabled', 'bed_recheck_minutes', 'scheduled_alarms']],
  ['二度寝検知アラーム', ['alarm_enabled', 'buzzer_enabled', 'buzzer_pin', 'buzzer_duration_sec', 'buzzer_pulse_sec', 'webhook_url']],
  ['通知', ['webhook_enabled', 'webhook_events', 'webhook_payload_format', 'webhook_timeout_sec']]
];
const fieldTypes = Object.fromEntries(fields);
const weekdayLabels = ['月', '火', '水', '木', '金', '土', '日'];
const fieldLabels = {
  log_path: 'ログ',
  status_path: '状態ファイル',
  person_weight_kg: '体重 kg',
  sample_interval_sec: '読取間隔 秒',
  warmup_samples: 'ウォームアップ',
  median_samples: '中央値サンプル',
  moving_average_window: '平滑化',
  exit_ratio: '離床しきい値',
  return_ratio: '入床しきい値',
  monitor_sec: '監視時間 秒',
  confirm_sec: '確認時間 秒',
  data_pin: 'DATAピン',
  clock_pin: 'CLOCKピン',
  hx711_ready_timeout_sec: 'HX711待機 秒',
  alarm_enabled: '二度寝検知',
  buzzer_enabled: 'ブザー',
  buzzer_pin: 'ブザーピン',
  buzzer_duration_sec: '鳴動時間 秒',
  buzzer_pulse_sec: 'パルス 秒',
  scheduled_alarm_enabled: '時刻アラーム',
  bed_recheck_minutes: '再確認 分',
  webhook_enabled: 'Webhook',
  webhook_events: '通知イベント',
  webhook_payload_format: '形式',
  webhook_timeout_sec: 'タイムアウト 秒',
  webhook_url: 'Webhook URL'
};
let current = {};
let messageTimer = null;

function token() { return localStorage.getItem('twodosumi_token') || document.getElementById('token').value; }
function saveToken() { localStorage.setItem('twodosumi_token', document.getElementById('token').value); note('token saved'); }
function note(text) {
  const el = document.getElementById('message');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => el.classList.remove('show'), 3600);
}
function headers() { return {'Content-Type': 'application/json', 'X-2Dosumi-Token': token()}; }

async function api(path, opts={}) {
  const res = await fetch(path, {...opts, headers: headers()});
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'request failed');
  return data;
}

function renderSettings(settings) {
  current = settings;
  syncAlarmUi(Boolean(settings.alarm_enabled));
  syncScheduledAlarmUi(Boolean(settings.scheduled_alarm_enabled));
  renderAlarmPreview(settings.scheduled_alarms || []);
  const root = document.getElementById('settings');
  root.innerHTML = '';
  for (const [title, names] of fieldGroups) {
    const group = document.createElement('div');
    group.className = 'setting-group';
    if (names.includes('scheduled_alarms')) group.classList.add('wide');
    const heading = document.createElement('h3');
    heading.textContent = title;
    const fieldsRoot = document.createElement('div');
    fieldsRoot.className = 'setting-group-fields';
    group.appendChild(heading);
    group.appendChild(fieldsRoot);
    for (const name of names) {
      if (name === 'scheduled_alarms') fieldsRoot.appendChild(createScheduledAlarmEditor(settings.scheduled_alarms || []));
      else fieldsRoot.appendChild(createSettingField(name, fieldTypes[name], settings));
    }
    root.appendChild(group);
  }
}

function renderAlarmPreview(alarms) {
  const root = document.getElementById('alarm-preview-list');
  if (!root) return;
  root.innerHTML = '';
  const shown = alarms.filter(alarm => alarm.enabled !== false).slice(0, 3);
  if (!shown.length) {
    const empty = document.createElement('div');
    empty.className = 'alarm-preview-item';
    empty.innerHTML = '<span class="alarm-preview-time">--:--</span><span class="alarm-preview-meta"><strong>未設定</strong><span>アラームを追加してください</span></span><span class="pill off">OFF</span>';
    root.appendChild(empty);
    return;
  }
  for (const alarm of shown) {
    const item = document.createElement('div');
    item.className = 'alarm-preview-item';
    const days = (alarm.weekdays || []).map(day => weekdayLabels[day]).filter(Boolean).join(' ');
    item.innerHTML = `
      <span class="alarm-preview-time">${alarm.time || '--:--'}</span>
      <span class="alarm-preview-meta">
        <strong>${escapeHtml(alarm.label || 'アラーム')}</strong>
        <span>${days || '曜日未設定'}</span>
      </span>
      <span class="pill">ON</span>
    `;
    root.appendChild(item);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[char]));
}

function syncAlarmUi(enabled) {
  const alarmInput = document.getElementById('quick_alarm_enabled');
  const alarmPill = document.getElementById('alarm-pill');
  if (alarmInput) alarmInput.checked = enabled;
  if (alarmPill) {
    alarmPill.textContent = enabled ? 'ON' : 'OFF';
    alarmPill.classList.toggle('off', !enabled);
  }
}

async function toggleAlarm(enabled) {
  try {
    await api('/api/settings', {method: 'POST', body: JSON.stringify({settings: {alarm_enabled: enabled}})});
    current.alarm_enabled = enabled;
    syncAlarmUi(enabled);
    const fullField = document.getElementById('set_alarm_enabled');
    if (fullField) fullField.checked = enabled;
    note(enabled ? 'alarm enabled' : 'alarm disabled');
  } catch (err) {
    syncAlarmUi(Boolean(current.alarm_enabled));
    note(err.message);
  }
}

function syncScheduledAlarmUi(enabled) {
  const input = document.getElementById('quick_scheduled_alarm_enabled');
  const pill = document.getElementById('scheduled-alarm-pill');
  if (input) input.checked = enabled;
  if (pill) {
    pill.textContent = enabled ? 'ON' : 'OFF';
    pill.classList.toggle('off', !enabled);
  }
}

async function toggleScheduledAlarm(enabled) {
  try {
    await api('/api/settings', {method: 'POST', body: JSON.stringify({settings: {scheduled_alarm_enabled: enabled}})});
    current.scheduled_alarm_enabled = enabled;
    syncScheduledAlarmUi(enabled);
    const fullField = document.getElementById('set_scheduled_alarm_enabled');
    if (fullField) fullField.checked = enabled;
    note(enabled ? 'scheduled alarms enabled' : 'scheduled alarms disabled');
  } catch (err) {
    syncScheduledAlarmUi(Boolean(current.scheduled_alarm_enabled));
    note(err.message);
  }
}

function createSettingField(name, type, settings) {
    const label = document.createElement('label');
    label.textContent = fieldLabels[name] || name;
    let input;
    if (name === 'webhook_payload_format') {
      input = document.createElement('select');
      for (const value of ['discord', 'json']) {
        const opt = document.createElement('option');
        opt.value = value; opt.textContent = value; input.appendChild(opt);
      }
    } else {
      input = document.createElement('input');
      input.type = type;
      if (type === 'number') input.step = 'any';
    }
    input.id = 'set_' + name;
    if (name === 'webhook_events') input.value = (settings[name] || []).join(',');
    else if (type === 'checkbox') input.checked = Boolean(settings[name]);
    else input.value = settings[name] ?? '';
    label.appendChild(input);
    return label;
}

function createScheduledAlarmEditor(alarms) {
  const wrap = document.createElement('div');
  wrap.className = 'scheduled-editor full';
  wrap.id = 'scheduled_alarm_editor';
  for (const alarm of alarms) wrap.appendChild(createScheduledAlarmRow(alarm));
  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'secondary';
  add.textContent = 'アラームを追加';
  add.onclick = () => addScheduledAlarm();
  wrap.appendChild(add);
  return wrap;
}

function createScheduledAlarmRow(alarm) {
  const row = document.createElement('div');
  row.className = 'scheduled-row';
  row.dataset.id = alarm.id || `alarm_${Date.now()}`;

  const timeBlock = document.createElement('div');
  timeBlock.className = 'scheduled-time-block';
  const enabled = document.createElement('label');
  enabled.className = 'switch';
  enabled.setAttribute('aria-label', 'アラーム');
  const enabledInput = document.createElement('input');
  enabledInput.className = 'scheduled-enabled';
  enabledInput.type = 'checkbox';
  enabledInput.checked = alarm.enabled !== false;
  const enabledSlider = document.createElement('span');
  enabledSlider.className = 'slider';
  enabled.appendChild(enabledInput);
  enabled.appendChild(enabledSlider);

  const timeInput = document.createElement('input');
  timeInput.className = 'scheduled-time';
  timeInput.type = 'time';
  timeInput.value = alarm.time || '07:00';
  timeBlock.appendChild(enabled);
  timeBlock.appendChild(timeInput);

  const detail = document.createElement('div');
  detail.className = 'scheduled-detail';
  const labelInput = document.createElement('input');
  labelInput.className = 'scheduled-label';
  labelInput.type = 'text';
  labelInput.placeholder = 'ラベル';
  labelInput.value = alarm.label || '';

  const weekdays = document.createElement('div');
  weekdays.className = 'weekday-row';
  const selected = new Set(alarm.weekdays || [0, 1, 2, 3, 4, 5, 6]);
  for (let day = 0; day < 7; day += 1) {
    const dayLabel = document.createElement('label');
    const dayInput = document.createElement('input');
    dayInput.type = 'checkbox';
    dayInput.className = 'scheduled-weekday';
    dayInput.value = String(day);
    dayInput.checked = selected.has(day);
    dayLabel.appendChild(dayInput);
    dayLabel.appendChild(document.createTextNode(weekdayLabels[day]));
    weekdays.appendChild(dayLabel);
  }
  detail.appendChild(labelInput);
  detail.appendChild(weekdays);

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'warn';
  remove.textContent = '削除';
  remove.onclick = () => row.remove();

  row.appendChild(timeBlock);
  row.appendChild(detail);
  row.appendChild(remove);
  return row;
}

function addScheduledAlarm() {
  const editor = document.getElementById('scheduled_alarm_editor');
  if (!editor) return;
  const button = editor.querySelector('button.secondary');
  const row = createScheduledAlarmRow({
    id: `alarm_${Date.now()}`,
    time: '07:00',
    enabled: true,
    label: '',
    weekdays: [0, 1, 2, 3, 4, 5, 6]
  });
  editor.insertBefore(row, button);
}

function collectScheduledAlarms() {
  return [...document.querySelectorAll('.scheduled-row')].map(row => ({
    id: row.dataset.id,
    time: row.querySelector('.scheduled-time').value || '07:00',
    enabled: row.querySelector('.scheduled-enabled').checked,
    label: row.querySelector('.scheduled-label').value,
    weekdays: [...row.querySelectorAll('.scheduled-weekday:checked')].map(el => Number(el.value))
  }));
}

async function loadSettings() {
  try {
    document.getElementById('token').value = token();
    const data = await api('/api/settings');
    renderSettings(data.settings);
    note('settings loaded');
  } catch (err) { note(err.message); }
}

async function saveSettings() {
  try {
    const settings = {};
    for (const [name, type] of fields) {
      const el = document.getElementById('set_' + name);
      if (name === 'webhook_events') settings[name] = el.value.split(',').map(v => v.trim()).filter(Boolean);
      else if (type === 'checkbox') settings[name] = el.checked;
      else if (type === 'number') settings[name] = Number(el.value);
      else settings[name] = el.value;
    }
    settings.scheduled_alarms = collectScheduledAlarms();
    await api('/api/settings', {method: 'POST', body: JSON.stringify({settings})});
    current = {...current, ...settings};
    renderAlarmPreview(settings.scheduled_alarms);
    note('settings saved');
  } catch (err) { note(err.message); }
}

function setText(id, value) { document.getElementById(id).textContent = value || '-'; }
function formatAlarm(alarm) {
  if (!alarm) return '-';
  const label = alarm.label ? ` ${alarm.label}` : '';
  return `${alarm.time}${label}`;
}
function updateStatusView(status) {
  const running = Boolean(status.managed_process_running || status.running);
  const runPill = document.getElementById('run-pill');
  runPill.textContent = running ? '稼働中' : '停止中';
  runPill.classList.toggle('off', !running);
  const timePill = document.getElementById('status-time');
  timePill.textContent = status.timestamp || '未取得';
  timePill.classList.toggle('off', !status.timestamp);
  setText('metric-state', status.state);
  setText('metric-event', status.event);
  const weight = status.smoothed_weight_kg == null ? '-' : `${Number(status.smoothed_weight_kg).toFixed(2)} kg`;
  setText('metric-weight', weight);
  setText('metric-process', running ? 'running' : 'stopped');
  setText('metric-next-alarm', formatAlarm(status.next_scheduled_alarm));
  const rechecks = status.pending_rechecks || [];
  setText('metric-recheck', rechecks.length ? `${rechecks.length} pending` : '-');
  setText('scheduled-alarm-next', status.next_scheduled_alarm ? `次: ${formatAlarm(status.next_scheduled_alarm)}` : '次のアラームは未設定です。');
  setText('hero-state', status.state);
  setText('hero-weight', weight);
  document.getElementById('status').textContent = JSON.stringify(status, null, 2);
}

async function loadStatus() {
  try {
    const data = await api('/api/status');
    updateStatusView(data.status);
  } catch (err) { note(err.message); }
}

async function post(path, body={}) {
  try {
    const data = await api(path, {method: 'POST', body: JSON.stringify(body)});
    note('ok');
    loadStatus();
    return data;
  } catch (err) { note(err.message); }
}

function calibrateZero() {
  post('/api/calibration/zero', {samples: Number(document.getElementById('cal_samples').value)});
}
function calibrateScale() {
  post('/api/calibration/scale', {
    samples: Number(document.getElementById('cal_samples').value),
    known_kg: Number(document.getElementById('known_kg').value)
  });
}

async function checkSensor() {
  const root = document.getElementById('sensor-check-result');
  root.className = 'sensor-check-result';
  root.textContent = '確認中...';
  try {
    const data = await api('/api/sensor/check', {
      method: 'POST',
      body: JSON.stringify({
        samples: Number(document.getElementById('cal_samples').value) || 10,
        interval_sec: 0.1
      })
    });
    renderSensorCheck(data.sensor, data.restarted);
    note(data.sensor.ok ? 'sensor check ok' : 'sensor check failed');
  } catch (err) {
    root.className = 'sensor-check-result fail';
    root.textContent = err.message;
    note(err.message);
  }
}

function renderSensorCheck(sensor, restarted) {
  const root = document.getElementById('sensor-check-result');
  root.className = `sensor-check-result ${sensor.ok ? 'ok' : 'fail'}`;
  const lines = [
    `${sensor.ok ? 'OK' : 'NG'}: ${sensor.message || ''}`,
    `reader: ${sensor.reader}`,
    `samples: ${sensor.samples_read}/${sensor.samples_requested}`,
    `duration: ${Number(sensor.duration_sec || 0).toFixed(2)} sec`
  ];
  if (sensor.raw_median != null) {
    lines.push(
      `raw: min=${Number(sensor.raw_min).toFixed(3)} max=${Number(sensor.raw_max).toFixed(3)} median=${Number(sensor.raw_median).toFixed(3)} span=${Number(sensor.raw_span).toFixed(3)}`
    );
  }
  if (sensor.weight_median_kg != null) {
    lines.push(`weight median: ${Number(sensor.weight_median_kg).toFixed(3)} kg`);
  }
  for (const warning of sensor.warnings || []) {
    lines.push(`WARNING: ${warning}`);
  }
  if (restarted) lines.push('検知プロセスを一時停止して再開しました。');
  root.textContent = lines.join('\n');
}

setInterval(loadStatus, 3000);
document.getElementById('token').value = token();
if (token()) loadSettings();
else loadStatus();
</script>
</body>
</html>
"""
