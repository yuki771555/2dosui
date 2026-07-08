from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import itertools
import math
import statistics
import time
from typing import Iterable

from .config import AppConfig


HX711_INVALID_RAW_VALUES = frozenset((-0x800000, -1, 0x7FFFFF))
HX711_READ_ATTEMPTS = 3


class SensorReader(ABC):
    @abstractmethod
    def read_raw(self) -> float:
        raise NotImplementedError

    def close(self) -> None:
        pass


@dataclass
class SensorCheckResult:
    ok: bool
    reader: str
    samples_requested: int
    samples_read: int
    raw_min: float | None = None
    raw_max: float | None = None
    raw_median: float | None = None
    raw_span: float | None = None
    weight_median_kg: float | None = None
    duration_sec: float = 0.0
    message: str = ""
    warnings: list[str] | None = None


class MockReader(SensorReader):
    def __init__(self, config: AppConfig) -> None:
        points: list[float] = []
        for step in config.mock_sequence:
            samples = int(step["samples"])
            raw = config.zero_offset + float(step["weight_kg"]) * config.scale_factor
            points.extend([raw] * samples)
        if not points:
            points = [config.zero_offset]
        self._values = itertools.chain(points, itertools.repeat(points[-1]))

    def read_raw(self) -> float:
        return float(next(self._values))


class AdafruitHX711AggregateReader(SensorReader):
    def __init__(self, config: AppConfig) -> None:
        self._gpio = None
        self._gpio_data_pin: int | None = None
        self._gpio_clock_pin: int | None = None
        self._data = None
        self._clock = None
        self._timeout_sec = config.hx711_ready_timeout_sec
        self._data_pin_name = config.data_pin
        self._clock_pin_name = config.clock_pin

        GPIO = None
        try:
            import RPi.GPIO as candidate_gpio

            data_pin = _board_pin_to_bcm(config.data_pin)
            clock_pin = _board_pin_to_bcm(config.clock_pin)
            candidate_gpio.setwarnings(False)
            candidate_gpio.setmode(candidate_gpio.BCM)
            candidate_gpio.setup(data_pin, candidate_gpio.IN)
            candidate_gpio.setup(
                clock_pin, candidate_gpio.OUT, initial=candidate_gpio.LOW
            )
            GPIO = candidate_gpio
        except ImportError:
            GPIO = None
        except RuntimeError:
            try:
                candidate_gpio.cleanup((data_pin, clock_pin))
            except RuntimeError:
                pass
            GPIO = None

        if GPIO is not None:
            self._gpio = GPIO
            self._gpio_data_pin = data_pin
            self._gpio_clock_pin = clock_pin
            return

        try:
            import board
            import digitalio
        except ImportError as exc:
            raise RuntimeError(
                "Install Pi dependencies with: python3 -m pip install -r requirements-pi.txt"
            ) from exc

        data_pin = getattr(board, config.data_pin)
        clock_pin = getattr(board, config.clock_pin)
        data = digitalio.DigitalInOut(data_pin)
        data.direction = digitalio.Direction.INPUT
        clock = digitalio.DigitalInOut(clock_pin)
        clock.direction = digitalio.Direction.OUTPUT
        clock.value = False

        self._data = data
        self._clock = clock

    def read_raw(self) -> float:
        last_value = 0
        for _ in range(HX711_READ_ATTEMPTS):
            self._wait_until_ready()
            last_value = self._read_channel_a_gain_128()
            if last_value not in HX711_INVALID_RAW_VALUES:
                return float(last_value)
        raise RuntimeError(
            "HX711 returned an invalid endpoint value "
            f"({last_value}) {HX711_READ_ATTEMPTS} times. "
            "This usually means SCK timing interference or an unstable GPIO backend."
        )

    def close(self) -> None:
        if self._gpio is not None:
            pins = [
                pin
                for pin in (self._gpio_data_pin, self._gpio_clock_pin)
                if pin is not None
            ]
            if pins:
                self._gpio.cleanup(pins)
            self._gpio = None
        for pin in (self._data, self._clock):
            if pin is not None:
                pin.deinit()
        self._data = None
        self._clock = None

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self._timeout_sec
        while self._read_data_pin():
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "HX711 DOUT stayed HIGH and no sample became ready. "
                    f"Check VCC=3.3V, GND, DT/DOUT={self._data_pin_name}, "
                    f"SCK/CLK={self._clock_pin_name}, and the 4-load-cell bridge wiring."
                )
            time.sleep(0.01)

    def _read_channel_a_gain_128(self) -> int:
        value = 0
        try:
            for _ in range(24):
                self._set_clock_pin(True)
                value = (value << 1) | int(self._read_data_pin())
                self._set_clock_pin(False)

            # One extra pulse selects channel A with gain 128 for the next sample.
            self._set_clock_pin(True)
            self._set_clock_pin(False)
        finally:
            self._set_clock_pin(False)

        if value & 0x800000:
            value -= 0x1000000
        return value

    def _read_data_pin(self) -> bool:
        if self._gpio is not None:
            return bool(self._gpio.input(self._gpio_data_pin))
        return bool(self._data.value)

    def _set_clock_pin(self, value: bool) -> None:
        if self._gpio is not None:
            self._gpio.output(self._gpio_clock_pin, self._gpio.HIGH if value else self._gpio.LOW)
            return
        self._clock.value = value


def _board_pin_to_bcm(pin_name: str) -> int:
    if not pin_name.startswith("D"):
        raise ValueError(f"Unsupported Raspberry Pi GPIO pin name: {pin_name}")
    try:
        return int(pin_name[1:])
    except ValueError as exc:
        raise ValueError(f"Unsupported Raspberry Pi GPIO pin name: {pin_name}") from exc


def create_reader(config: AppConfig) -> SensorReader:
    if config.reader == "mock":
        return MockReader(config)
    if config.reader == "adafruit_hx711":
        return AdafruitHX711AggregateReader(config)
    raise ValueError(f"Unsupported reader: {config.reader}")


def median_raw(reader: SensorReader, samples: int, interval_sec: float = 0.02) -> float:
    values: list[float] = []
    for index in range(max(1, samples)):
        values.append(reader.read_raw())
        if index < samples - 1 and interval_sec > 0:
            time.sleep(interval_sec)
    return float(statistics.median(values))


def warmup(reader: SensorReader, samples: int) -> None:
    for _ in range(max(0, samples)):
        reader.read_raw()


def moving_average(values: Iterable[float]) -> float:
    data = list(values)
    if not data:
        return 0.0
    return sum(data) / len(data)


def check_sensor(config: AppConfig, samples: int = 10, interval_sec: float = 0.1) -> SensorCheckResult:
    requested = max(1, int(samples))
    warnings: list[str] = []
    values: list[float] = []
    started = time.monotonic()
    reader: SensorReader | None = None
    try:
        reader = create_reader(config)
        warmup(reader, min(max(0, config.warmup_samples), 5))
        for index in range(requested):
            raw = float(reader.read_raw())
            if not math.isfinite(raw):
                raise RuntimeError(f"sensor returned a non-finite raw value: {raw}")
            values.append(raw)
            if index < requested - 1 and interval_sec > 0:
                time.sleep(interval_sec)
    except Exception as exc:
        return SensorCheckResult(
            ok=False,
            reader=config.reader,
            samples_requested=requested,
            samples_read=len(values),
            duration_sec=time.monotonic() - started,
            message=str(exc),
            warnings=warnings,
        )
    finally:
        if reader is not None:
            reader.close()

    raw_min = min(values)
    raw_max = max(values)
    raw_median = float(statistics.median(values))
    raw_span = raw_max - raw_min
    weight_median_kg = None
    if config.scale_factor != 0:
        weight_median_kg = (raw_median - config.zero_offset) / config.scale_factor
    if raw_span == 0 and requested > 1:
        warnings.append(
            "Raw values did not change during the check. This can be normal if the bed was still, "
            "but press/release the bed once if you want to confirm load response."
        )
    if config.reader == "mock":
        warnings.append("Mock reader is active; this does not verify Raspberry Pi GPIO wiring.")

    return SensorCheckResult(
        ok=True,
        reader=config.reader,
        samples_requested=requested,
        samples_read=len(values),
        raw_min=raw_min,
        raw_max=raw_max,
        raw_median=raw_median,
        raw_span=raw_span,
        weight_median_kg=weight_median_kg,
        duration_sec=time.monotonic() - started,
        message="sensor samples read successfully",
        warnings=warnings,
    )
