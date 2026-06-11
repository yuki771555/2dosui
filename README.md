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

