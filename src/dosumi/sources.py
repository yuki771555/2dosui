from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass
from typing import Iterator, Protocol

from .config import Hx711Config


@dataclass(frozen=True)
class Reading:
    timestamp: float
    raw: float
    weight_kg: float
    ratio: float


class WeightSource(Protocol):
    def readings(self) -> Iterator[Reading]:
        ...


class SimulatedSource:
    def __init__(self, body_weight_kg: float, interval_sec: float = 1.0, speed: float = 1.0):
        self.body_weight_kg = body_weight_kg
        self.interval_sec = interval_sec
        self.speed = max(speed, 0.01)

    def readings(self) -> Iterator[Reading]:
        start = time.time()
        sim_time = 0.0
        while True:
            weight = self._weight_at(sim_time)
            noise = random.uniform(-0.4, 0.4)
            measured = max(0.0, weight + noise)
            ratio = measured / self.body_weight_kg if self.body_weight_kg else 0.0
            yield Reading(start + sim_time, measured * 1000.0, measured, ratio)
            time.sleep(self.interval_sec / self.speed)
            sim_time += self.interval_sec

    def _weight_at(self, t: float) -> float:
        cycle = t % 520.0
        if cycle < 60:
            return self.body_weight_kg
        if cycle < 110:
            return 0.0
        if cycle < 170:
            return 0.0
        if cycle < 370:
            return self.body_weight_kg
        if cycle < 430:
            return 0.0
        return self.body_weight_kg * (0.04 + 0.03 * math.sin(cycle / 5.0))


class Hx711Source:
    def __init__(self, config: Hx711Config, body_weight_kg: float, interval_sec: float = 1.0):
        self.config = config
        self.body_weight_kg = body_weight_kg
        self.interval_sec = interval_sec
        self.hx = self._init_hx711()

    def _init_hx711(self):
        try:
            from hx711 import HX711
        except ImportError as exc:
            raise RuntimeError(
                "hx711 library is not installed. Run: python -m pip install hx711"
            ) from exc

        hx = HX711(dout_pin=self.config.dout_pin, pd_sck_pin=self.config.sck_pin)
        hx.reset()
        return hx

    def read_raw(self) -> float:
        value = self.hx.get_raw_data_mean(readings=self.config.readings)
        if isinstance(value, (list, tuple)):
            return float(statistics.mean(value))
        return float(value)

    def readings(self) -> Iterator[Reading]:
        while True:
            raw = self.read_raw()
            weight = (raw - self.config.zero_offset) / self.config.scale_factor
            ratio = weight / self.body_weight_kg if self.body_weight_kg else 0.0
            yield Reading(time.time(), raw, weight, ratio)
            time.sleep(self.interval_sec)
