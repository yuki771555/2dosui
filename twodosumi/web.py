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
    Secrets,
    load_config,
    load_secrets,
    save_config,
    save_secrets,
    validate_config,
)
from .notifier import send_test_webhook
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
        "webhook_timeout_sec",
    }
    bool_fields = {"alarm_enabled", "buzzer_enabled", "webhook_enabled"}
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
      --bg: #edf3f5;
      --panel: #ffffff;
      --panel-soft: #f5f8fa;
      --ink: #16202a;
      --muted: #60717d;
      --line: #d3dfe5;
      --accent: #0b7f86;
      --accent-dark: #075f65;
      --accent-soft: #e4f4f4;
      --good: #1a755b;
      --warn: #b44a34;
      --warm: #c4822b;
      --shadow: 0 24px 62px rgba(23, 40, 52, 0.16);
      --button-shadow: 0 10px 18px rgba(11, 127, 134, 0.2);
    }
    * { box-sizing: border-box; }
    body {
      min-height: 100vh;
      margin: 0;
      background:
        linear-gradient(rgba(255, 255, 255, 0.42) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.42) 1px, transparent 1px),
        linear-gradient(140deg, #f8fbfc 0%, var(--bg) 47%, #dce8ec 100%);
      background-size: 34px 34px, 34px 34px, auto;
      color: var(--ink);
    }
    main { max-width: 1220px; margin: 0 auto; padding: 24px; }
    h1, h2 { margin: 0; letter-spacing: 0; }
    h1 { font-size: clamp(30px, 5vw, 48px); line-height: 0.98; }
    h2 { font-size: 16px; }
    p { margin: 0; }
    .app-frame {
      position: relative;
      overflow: hidden;
      border: 1px solid rgba(93, 117, 130, 0.36);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.9);
      box-shadow: 0 28px 80px rgba(26, 44, 57, 0.2);
      backdrop-filter: blur(16px);
    }
    .app-frame::before {
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      border: 6px solid rgba(255, 255, 255, 0.64);
      border-radius: inherit;
    }
    .app-bar {
      position: relative;
      z-index: 1;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      min-height: 64px;
      padding: 0 20px;
      border-bottom: 1px solid rgba(126, 150, 162, 0.24);
      background: linear-gradient(90deg, rgba(255, 255, 255, 0.96), rgba(245, 249, 250, 0.92));
    }
    .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      background:
        linear-gradient(135deg, #0b7f86, #16323b 72%),
        #16323b;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.24), 0 10px 20px rgba(11, 127, 134, 0.22);
    }
    .brand-text { display: grid; gap: 2px; min-width: 0; }
    .brand strong { font-size: 17px; font-weight: 900; }
    .brand span { color: var(--muted); font-size: 12px; font-weight: 750; }
    .content { position: relative; z-index: 1; padding: 14px; }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.18fr) minmax(300px, 0.82fr);
      gap: 12px;
      min-height: 238px;
      overflow: hidden;
      border: 1px solid rgba(194, 211, 218, 0.96);
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(240, 249, 249, 0.98) 62%, rgba(247, 241, 232, 0.9)),
        linear-gradient(90deg, rgba(11, 127, 134, 0.1), transparent 58%);
      box-shadow: var(--shadow);
    }
    .hero-copy { display: flex; flex-direction: column; justify-content: space-between; gap: 26px; padding: 30px; }
    .hero-title { display: grid; gap: 13px; }
    .hero-kicker {
      width: fit-content;
      padding: 5px 9px;
      border: 1px solid rgba(11, 127, 134, 0.22);
      border-radius: 999px;
      background: rgba(228, 244, 244, 0.8);
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
      border: 1px solid rgba(202, 217, 224, 0.92);
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
      border: 1px solid rgba(202, 217, 224, 0.92);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      background: linear-gradient(90deg, rgba(228, 244, 244, 0.72), #fff 42%);
    }
    .alarm-card strong { display: block; font-size: 15px; }
    .alarm-card span { display: block; margin-top: 3px; color: var(--muted); font-size: 12px; line-height: 1.45; }
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
    .switch input:checked + .slider { background: linear-gradient(135deg, var(--accent), #167568); }
    .switch input:checked + .slider::after { transform: translateX(24px); }
    .top-actions { display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; align-items: center; }
    .shell { display: grid; grid-template-columns: 0.82fr 1.18fr; gap: 12px; margin-top: 12px; }
    section {
      background: rgba(255, 255, 255, 0.93);
      border: 1px solid rgba(216, 225, 231, 0.86);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 12px 28px rgba(31, 48, 63, 0.075);
    }
    .stack { display: grid; gap: 14px; align-content: start; }
    .section-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(184px, 1fr)); gap: 12px; }
    .settings-grid { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
    .setting-group {
      display: grid;
      gap: 12px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(180deg, #ffffff, var(--panel-soft));
    }
    .setting-group h3 {
      margin: 0;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(211, 223, 229, 0.82);
      font-size: 13px;
      letter-spacing: 0;
    }
    .setting-group-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
    label { display: grid; gap: 6px; font-size: 12px; color: var(--muted); font-weight: 650; }
    input, select {
      width: 100%;
      min-height: 44px;
      font: inherit;
      padding: 9px 10px;
      border: 1px solid #bdcbd3;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.92);
      color: var(--ink);
      outline: none;
    }
    input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(15, 120, 133, 0.14); }
    input[type="checkbox"] { width: 20px; min-height: 20px; accent-color: var(--accent); }
    button {
      min-height: 44px;
      font: inherit;
      font-weight: 750;
      padding: 9px 13px;
      border: 0;
      border-radius: 6px;
      background: linear-gradient(180deg, #0d8a91, var(--accent-dark));
      color: white;
      cursor: pointer;
      box-shadow: var(--button-shadow);
      transition: transform 140ms ease, box-shadow 140ms ease, background 140ms ease;
    }
    button:hover { transform: translateY(-1px); box-shadow: 0 12px 22px rgba(11, 127, 134, 0.24); }
    button:active { transform: translateY(0); box-shadow: var(--button-shadow); }
    button.secondary { background: linear-gradient(180deg, #5d6f7b, #455560); box-shadow: 0 10px 18px rgba(69, 85, 96, 0.18); }
    button.secondary:hover { background: linear-gradient(180deg, #556671, #3f4e58); box-shadow: 0 12px 22px rgba(69, 85, 96, 0.22); }
    button.warn { background: linear-gradient(180deg, #bd553d, #963927); box-shadow: 0 10px 18px rgba(180, 74, 52, 0.18); }
    button.warn:hover { background: linear-gradient(180deg, #ad4c37, #873221); box-shadow: 0 12px 22px rgba(180, 74, 52, 0.22); }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .status-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
    .metric {
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, #ffffff, var(--panel-soft));
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
      background: linear-gradient(90deg, var(--accent), var(--warm));
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
      background: #e5f4ee;
      color: var(--good);
      white-space: nowrap;
    }
    .pill.off { border-color: rgba(180, 74, 52, 0.18); background: #f6e9e5; color: var(--warn); }
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
      .shell { grid-template-columns: 1fr; }
      .status-cards { grid-template-columns: 1fr; }
      button { flex: 1 1 132px; }
      .alarm-card { align-items: flex-start; }
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
        <div class="stack">
          <section>
            <div class="section-head"><h2>2度寝アラーム</h2><span id="alarm-pill" class="pill off">OFF</span></div>
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

          <section>
            <div class="section-head"><h2>キャリブレーション</h2></div>
            <div class="grid">
              <label>samples<input id="cal_samples" type="number" value="30" min="1"></label>
              <label>known kg<input id="known_kg" type="number" step="0.1" min="0"></label>
            </div>
            <div class="actions">
              <button onclick="calibrateZero()">ゼロ校正</button>
              <button onclick="calibrateScale()">重量校正</button>
            </div>
          </section>
        </div>

        <section>
          <div class="section-head">
            <h2>状態</h2>
            <span id="status-time" class="pill off">未取得</span>
          </div>
          <div class="status-cards">
            <div class="metric"><span>state</span><strong id="metric-state">-</strong></div>
            <div class="metric"><span>event</span><strong id="metric-event">-</strong></div>
            <div class="metric"><span>weight</span><strong id="metric-weight">-</strong></div>
            <div class="metric"><span>process</span><strong id="metric-process">-</strong></div>
          </div>
          <pre id="status" class="status">未取得</pre>
        </section>

        <section class="full">
          <div class="section-head">
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
  ['webhook_enabled','checkbox'], ['webhook_events','text'],
  ['webhook_payload_format','select'], ['webhook_timeout_sec','number'], ['webhook_url','password']
];
const fieldGroups = [
  ['基本', ['person_weight_kg', 'sample_interval_sec', 'log_path', 'status_path']],
  ['検知', ['exit_ratio', 'return_ratio', 'monitor_sec', 'confirm_sec', 'moving_average_window']],
  ['センサー', ['warmup_samples', 'median_samples', 'data_pin', 'clock_pin', 'hx711_ready_timeout_sec']],
  ['アラーム', ['alarm_enabled', 'buzzer_enabled', 'buzzer_pin', 'buzzer_duration_sec', 'buzzer_pulse_sec', 'webhook_url']],
  ['通知', ['webhook_enabled', 'webhook_events', 'webhook_payload_format', 'webhook_timeout_sec']]
];
const fieldTypes = Object.fromEntries(fields);
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
  const root = document.getElementById('settings');
  root.innerHTML = '';
  for (const [title, names] of fieldGroups) {
    const group = document.createElement('div');
    group.className = 'setting-group';
    const heading = document.createElement('h3');
    heading.textContent = title;
    const fieldsRoot = document.createElement('div');
    fieldsRoot.className = 'setting-group-fields';
    group.appendChild(heading);
    group.appendChild(fieldsRoot);
    for (const name of names) {
      fieldsRoot.appendChild(createSettingField(name, fieldTypes[name], settings));
    }
    root.appendChild(group);
  }
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

function createSettingField(name, type, settings) {
    const label = document.createElement('label');
    label.textContent = name;
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
    await api('/api/settings', {method: 'POST', body: JSON.stringify({settings})});
    note('settings saved');
  } catch (err) { note(err.message); }
}

function setText(id, value) { document.getElementById(id).textContent = value || '-'; }
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

setInterval(loadStatus, 3000);
document.getElementById('token').value = token();
</script>
</body>
</html>
"""
