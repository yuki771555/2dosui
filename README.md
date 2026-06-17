# 2dosumi

Raspberry Pi + HX711 + load cells project for detecting return-to-bed events.

## Local mock run

```powershell
python -m twodosumi run --config config/mock.fast.json --max-samples 25
```

## Web UI and webhook notifications

Install dependencies on the Raspberry Pi, then start the Web UI:

```bash
python3 -m pip install -r requirements-pi.txt
python3 -m twodosumi web --config config/pi.aggregate.json --secrets config/secrets.json --host 127.0.0.1 --port 8080
```

On first launch, `config/secrets.json` is created with a `web_ui_token`.
Open the UI through Tailscale Serve:

```bash
tailscale serve --bg 8080
```

The Web UI can edit thresholds and timing settings, start/stop detection, check sensor reads, run zero and scale calibration, and test webhook delivery. Use a Discord webhook URL with `webhook_payload_format=discord`, or set the format to `json` for a generic webhook endpoint.

The second-sleep alarm can be turned on or off from the Web UI. When `alarm_enabled` is on, `second_sleep_detected` sends a Discord webhook using `config/secrets.json` and pulses the Raspberry Pi buzzer. The default buzzer pin is `board.D13`; use an active buzzer or a suitable transistor/driver circuit for your buzzer module.

To start the Web UI automatically when the Pi boots:

```bash
chmod +x scripts/install_twodosumi_web_service.sh
./scripts/install_twodosumi_web_service.sh
tailscale serve --bg 8080
```

The installer defaults to `APP_DIR=/home/yuki/2dosumi`, `APP_USER=yuki`, and port `8080`. Override them if needed:

```bash
APP_DIR=/home/pi/2dosumi APP_USER=pi PORT=8080 ./scripts/install_twodosumi_web_service.sh
```

Useful checks:

```bash
systemctl status twodosumi-web.service --no-pager
journalctl -u twodosumi-web.service -f
tailscale serve status
```

## Raspberry Pi setup

For the full deployment flow, including copying files to the Pi, first sensor verification, calibration, and systemd setup, see [docs/raspberry_pi_deploy.md](docs/raspberry_pi_deploy.md).

```bash
python3 -m pip install -r requirements-pi.txt
python3 -m twodosumi check-sensor --config config/pi.aggregate.json --samples 10
python3 -m twodosumi calibrate-zero --config config/pi.aggregate.json
python3 -m twodosumi calibrate-scale --config config/pi.aggregate.json --known-kg 8
python3 -m twodosumi run --config config/pi.aggregate.json --secrets config/secrets.json
```

The current Pi config uses HX711 DATA on `board.D6` and SCK on `board.D5`.

## 4 load cell wiring

This project assumes four half-bridge load cells combined into one HX711 channel.
The program reads one aggregate weight value, not four independent corner values.

| HX711 terminal | Connect to |
| --- | --- |
| `E+` | `LC1 + LC2` |
| `E-` | `LC3 + LC4` |
| `A+` | `LC1 + LC3` |
| `A-` | `LC2 + LC4` |

HX711 to Raspberry Pi:

| HX711 | Raspberry Pi 4 |
| --- | --- |
| `VCC` | Pin 1 `3.3V` |
| `GND` | Pin 6 `GND` |
| `DT` / `DOUT` | Pin 31 `GPIO6` (`board.D6`) |
| `SCK` / `CLK` | Pin 29 `GPIO5` (`board.D5`) |

Use 3.3V for HX711 VCC first. Do not feed a 5V signal into Raspberry Pi GPIO.
