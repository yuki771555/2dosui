from __future__ import annotations

from abc import ABC, abstractmethod
import itertools
import statistics
import time
from typing import Iterable

from .config import AppConfig


class SensorReader(ABC):
    @abstractmethod
    def read_raw(self) -> float:
        raise NotImplementedError


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
        self._timeout_sec = config.hx711_ready_timeout_sec
        self._data_pin_name = config.data_pin
        self._clock_pin_name = config.clock_pin

    def read_raw(self) -> float:
        self._wait_until_ready()
        return float(self._read_channel_a_gain_128())

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self._timeout_sec
        while self._data.value:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "HX711 DOUT stayed HIGH and no sample became ready. "
                    f"Check VCC=3.3V, GND, DT/DOUT={self._data_pin_name}, "
                    f"SCK/CLK={self._clock_pin_name}, and the 4-load-cell bridge wiring."
                )
            time.sleep(0.01)

    def _read_channel_a_gain_128(self) -> int:
        value = 0
        for _ in range(24):
            self._clock.value = True
            time.sleep(0.000001)
            value = (value << 1) | int(self._data.value)
            self._clock.value = False
            time.sleep(0.000001)

        # One extra pulse selects channel A with gain 128 for the next sample.
        self._clock.value = True
        time.sleep(0.000001)
        self._clock.value = False

        if value & 0x800000:
            value -= 0x1000000
        return value


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
