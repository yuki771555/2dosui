# Raspberry Pi deployment

This guide deploys 2dosumi to a Raspberry Pi, confirms the HX711/load-cell sensor can be read, calibrates it, and starts the Web UI as a boot service.

## 1. Copy the project to the Pi

From this Windows project folder:

```powershell
.\scripts\deploy_pi.ps1 -HostName 192.168.137.105 -User yuki -RemoteDir /home/yuki/2dosumi
```

Adjust `HostName`, `User`, and `RemoteDir` for your Pi.

## 2. Install dependencies on the Pi

SSH into the Pi:

```bash
ssh yuki@192.168.137.105
cd /home/yuki/2dosumi
python3 -m pip install -r requirements-pi.txt
```

The default Pi config uses:

| HX711 | Raspberry Pi |
| --- | --- |
| DT / DOUT | GPIO6 / `board.D6` |
| SCK / CLK | GPIO5 / `board.D5` |
| VCC | 3.3V |
| GND | GND |

## 3. First sensor check

Before calibration, verify the Pi can read raw samples:

```bash
python3 -m twodosumi check-sensor --config config/pi.aggregate.json --samples 10
```

Expected:

- `ok=True`
- `samples=10/10`
- raw `min`, `max`, and `median` values are printed

If it fails with `HX711 DOUT stayed HIGH`, check HX711 power, ground, DT/DOUT, SCK/CLK, and the load-cell bridge wiring.

You can also run this from the Web UI with the `センサー確認` button in the calibration section. It temporarily stops the managed detection process if needed, reads samples, and restarts it afterward.

## 4. Calibrate

With the bed empty:

```bash
python3 -m twodosumi calibrate-zero --config config/pi.aggregate.json
```

Put a known weight on the bed and run:

```bash
python3 -m twodosumi calibrate-scale --config config/pi.aggregate.json --known-kg 8
```

Replace `8` with the actual known weight in kg.

Run the sensor check again. The `weight_median_kg` should be close to the current load.

## 5. Start the Web UI manually

```bash
python3 -m twodosumi web --config config/pi.aggregate.json --secrets config/secrets.json --host 127.0.0.1 --port 8080
```

On first launch, `config/secrets.json` is created with a `web_ui_token`.

Expose it through Tailscale:

```bash
tailscale serve --bg 8080
```

## 6. Install the boot service

```bash
chmod +x scripts/install_twodosumi_web_service.sh
./scripts/install_twodosumi_web_service.sh
tailscale serve --bg 8080
```

Useful checks:

```bash
systemctl status twodosumi-web.service --no-pager
journalctl -u twodosumi-web.service -f
tailscale serve status
```

## 7. Daily operation

Open the Web UI, enter the `web_ui_token`, then:

1. Run `センサー確認`.
2. Check the live weight/status.
3. Configure scheduled alarms.
4. Press `開始` to start detection.

