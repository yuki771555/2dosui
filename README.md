# 2dosumi

Raspberry Pi + HX711 + load cells project for detecting return-to-bed events.

## Local mock run

```powershell
python -m twodosumi run --config config/mock.fast.json --max-samples 25
```

## Raspberry Pi setup

```bash
python3 -m pip install -r requirements-pi.txt
python3 -m twodosumi calibrate-zero --config config/pi.aggregate.json
python3 -m twodosumi calibrate-scale --config config/pi.aggregate.json --known-kg 8
python3 -m twodosumi run --config config/pi.aggregate.json
```

The initial Pi config uses HX711 DATA on `board.D5` and SCK on `board.D6`.

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
| `DT` / `DOUT` | Pin 29 `GPIO5` (`board.D5`) |
| `SCK` / `CLK` | Pin 31 `GPIO6` (`board.D6`) |

Use 3.3V for HX711 VCC first. Do not feed a 5V signal into Raspberry Pi GPIO.
