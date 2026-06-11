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
            from adafruit_hx711.analog_in import AnalogIn
            from adafruit_hx711.hx711 import HX711
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

        hx711 = HX711(data, clock)
        self._channel_a = AnalogIn(hx711, HX711.CHAN_A_GAIN_128)

    def read_raw(self) -> float:
        return float(self._channel_a.value)


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

