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
        "webhook_timeout_sec",
    }
    bool_fields = {"webhook_enabled"}
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
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #17202a; }
    main { max-width: 980px; margin: 0 auto; padding: 20px; }
    h1 { font-size: 28px; margin: 0 0 16px; }
    h2 { font-size: 18px; margin: 0 0 12px; }
    section { background: white; border: 1px solid #dde2e8; border-radius: 8px; padding: 16px; margin: 12px 0; }
    label { display: grid; gap: 4px; font-size: 13px; color: #46515c; }
    input, select { font: inherit; padding: 9px; border: 1px solid #b8c0ca; border-radius: 6px; background: white; color: #17202a; }
    button { font: inherit; padding: 9px 12px; border: 0; border-radius: 6px; background: #146c94; color: white; cursor: pointer; }
    button.secondary { background: #52616f; }
    button.warn { background: #a53f2b; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .status { white-space: pre-wrap; font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
    .message { min-height: 22px; font-weight: 600; }
    @media (prefers-color-scheme: dark) {
      body { background: #111820; color: #ecf1f6; }
      section, input, select { background: #17202a; color: #ecf1f6; border-color: #324252; }
    }
  </style>
</head>
<body>
<main>
  <h1>2dosumi</h1>
  <section>
    <h2>認証</h2>
    <div class="grid">
      <label>Web UI Token<input id="token" type="password"></label>
    </div>
    <div class="actions">
      <button onclick="saveToken()">保存</button>
      <button class="secondary" onclick="loadSettings()">読み込み</button>
    </div>
  </section>

  <section>
    <h2>状態</h2>
    <div class="actions">
      <button onclick="post('/api/run/start')">開始</button>
      <button class="warn" onclick="post('/api/run/stop')">停止</button>
      <button class="secondary" onclick="loadStatus()">更新</button>
    </div>
    <pre id="status" class="status">未取得</pre>
  </section>

  <section>
    <h2>設定</h2>
    <div id="settings" class="grid"></div>
    <div class="actions">
      <button onclick="saveSettings()">設定を保存</button>
      <button class="secondary" onclick="post('/api/test-webhook')">Webhookテスト</button>
    </div>
  </section>

  <section>
    <h2>キャリブレーション</h2>
    <div class="grid">
      <label>samples<input id="cal_samples" type="number" value="30" min="1"></label>
      <label>known kg<input id="known_kg" type="number" step="0.1" min="0"></label>
    </div>
    <div class="actions">
      <button onclick="calibrateZero()">ゼロ校正</button>
      <button onclick="calibrateScale()">重量校正</button>
    </div>
  </section>

  <p id="message" class="message"></p>
</main>
<script>
const fields = [
  ['log_path','text'], ['status_path','text'], ['person_weight_kg','number'],
  ['sample_interval_sec','number'], ['warmup_samples','number'], ['median_samples','number'],
  ['moving_average_window','number'], ['exit_ratio','number'], ['return_ratio','number'],
  ['monitor_sec','number'], ['confirm_sec','number'], ['data_pin','text'], ['clock_pin','text'],
  ['hx711_ready_timeout_sec','number'], ['webhook_enabled','checkbox'], ['webhook_events','text'],
  ['webhook_payload_format','select'], ['webhook_timeout_sec','number'], ['webhook_url','password']
];
let current = {};

function token() { return localStorage.getItem('twodosumi_token') || document.getElementById('token').value; }
function saveToken() { localStorage.setItem('twodosumi_token', document.getElementById('token').value); note('token saved'); }
function note(text) { document.getElementById('message').textContent = text; }
function headers() { return {'Content-Type': 'application/json', 'X-2Dosumi-Token': token()}; }

async function api(path, opts={}) {
  const res = await fetch(path, {...opts, headers: headers()});
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'request failed');
  return data;
}

function renderSettings(settings) {
  current = settings;
  const root = document.getElementById('settings');
  root.innerHTML = '';
  for (const [name, type] of fields) {
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
    root.appendChild(label);
  }
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

async function loadStatus() {
  try {
    const data = await api('/api/status');
    document.getElementById('status').textContent = JSON.stringify(data.status, null, 2);
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
