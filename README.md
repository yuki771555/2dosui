# 2dosui

Raspberry Pi + HX711 + load cells for detecting when someone leaves bed and returns during a monitoring window.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cp config.toml.example config.toml
cp .env.example .env
2dosumi run --source sim --speed 30 --max-samples 260
```

Set `DISCORD_WEBHOOK_URL` in `.env` to enable Discord alerts.

## Hardware Defaults

- HX711 DT: GPIO5
- HX711 SCK: GPIO6
- Buzzer: GPIO18

The buzzer is disabled by default in `config.toml.example` until the part is attached.

## Calibration

```bash
2dosumi calibrate-zero --source hx711
2dosumi calibrate-scale --source hx711 --known-kg 8
```

After the load cells arrive, confirm raw values first:

```bash
2dosumi run --source hx711 --max-samples 20
```

## systemd

Install the service after copying the project to the Pi:

```bash
sudo cp systemd/2dosumi.service /etc/systemd/system/2dosumi.service
sudo systemctl daemon-reload
sudo systemctl enable 2dosumi
sudo systemctl start 2dosumi
```

The service defaults to `--source hx711`.
