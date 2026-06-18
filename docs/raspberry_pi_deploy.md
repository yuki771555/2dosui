# Raspberry Pi deployment

This guide deploys 2dosumi to a Raspberry Pi, confirms the HX711/load-cell sensor can be read, calibrates it, and starts the Web UI as a boot service.

The deployment flow is:

- sync code from Windows to the Pi with `ssh` and `scp`
- keep the Pi's calibrated config and secrets on the Pi
- install dependencies into `/home/yuki/2dosumi/.venv`
- run the Web UI as `twodosumi-web.service`
- expose `127.0.0.1:8080` through Tailscale Serve

## 1. Confirm SSH access

From this Windows project folder, confirm the Pi is reachable:

```powershell
ssh yuki@192.168.137.105
```

The defaults used by the deploy script are:

| Setting | Default |
| --- | --- |
| HostName | `192.168.137.105` |
| User | `yuki` |
| RemoteDir | `/home/yuki/2dosumi` |
| Port | `8080` |

Adjust `HostName`, `User`, `RemoteDir`, and `Port` if your Pi differs.

## 2. Deploy from Windows

From this Windows project folder:

```powershell
.\scripts\deploy_pi.ps1 -HostName 192.168.137.105 -User yuki -RemoteDir /home/yuki/2dosumi
```

If you are intentionally testing the current uncommitted working tree, add `-AllowDirty`:

```powershell
.\scripts\deploy_pi.ps1 -AllowDirty
```

The script copies application code, docs, scripts, `requirements-pi.txt`, and `README.md`. It creates `config/pi.aggregate.json` only when the Pi does not already have one.

Do not overwrite the Pi's existing `config/pi.aggregate.json` or `config/secrets.json` during normal updates. Calibration values, Web UI settings, webhook settings, and the generated token live there.

The script also creates or refreshes `.venv`, installs Pi dependencies, installs/restarts `twodosumi-web.service`, and verifies:

```bash
curl http://127.0.0.1:8080/healthz
```

If virtual environment creation fails, install venv support on the Pi:

SSH into the Pi:

```bash
ssh yuki@192.168.137.105
sudo apt-get update
sudo apt-get install -y python3-venv
```

Then run the deploy script again from Windows.

The default Pi config uses:

| HX711 | Raspberry Pi |
| --- | --- |
| DT / DOUT | GPIO6 / `board.D6` |
| SCK / CLK | GPIO5 / `board.D5` |
| VCC | 3.3V |
| GND | GND |

## 3. Expose the Web UI with Tailscale

On the Pi, run once:

```bash
tailscale serve --bg 8080
tailscale serve status
```

The Flask service listens only on `127.0.0.1:8080`; Tailscale Serve is the intended remote access path.

On first Web UI launch, `config/secrets.json` is created with a `web_ui_token`. Check the service log to see it:

```bash
journalctl -u twodosumi-web.service --no-pager -n 50
```

## 4. First sensor check

Before calibration, verify the Pi can read raw samples:

```bash
cd /home/yuki/2dosumi
. .venv/bin/activate
python -m twodosumi check-sensor --config config/pi.aggregate.json --samples 10
```

Expected:

- `ok=True`
- `samples=10/10`
- raw `min`, `max`, and `median` values are printed

If it fails with `HX711 DOUT stayed HIGH`, check HX711 power, ground, DT/DOUT, SCK/CLK, and the load-cell bridge wiring.

You can also run this from the Web UI with the `センサー確認` button in the calibration section. It temporarily stops the managed detection process if needed, reads samples, and restarts it afterward.

## 5. Calibrate

With the bed empty:

```bash
python -m twodosumi calibrate-zero --config config/pi.aggregate.json
```

Put a known weight on the bed and run:

```bash
python -m twodosumi calibrate-scale --config config/pi.aggregate.json --known-kg 8
```

Replace `8` with the actual known weight in kg.

Run the sensor check again. The `weight_median_kg` should be close to the current load.

## 6. Service operation

Useful checks:

```bash
systemctl status twodosumi-web.service --no-pager
journalctl -u twodosumi-web.service -f
tailscale serve status
curl http://127.0.0.1:8080/healthz
```

To reinstall the service manually:

```bash
cd /home/yuki/2dosumi
APP_DIR=/home/yuki/2dosumi APP_USER=yuki PORT=8080 ./scripts/install_twodosumi_web_service.sh
```

To start the Web UI manually for debugging:

```bash
cd /home/yuki/2dosumi
. .venv/bin/activate
python -m twodosumi web --config config/pi.aggregate.json --secrets config/secrets.json --host 127.0.0.1 --port 8080
```

## 7. Daily operation

Open the Web UI through Tailscale, enter the `web_ui_token`, then:

1. Run `センサー確認`.
2. Check the live weight/status.
3. Configure scheduled alarms.
4. Press `開始` to start detection.

For later updates, run:

```powershell
.\scripts\deploy_pi.ps1
```

Use `-AllowDirty` only when you intentionally want to send uncommitted local changes to the Pi.
