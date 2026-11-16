"""Dependency-free EV parking simulator. The grid has no non-charger loads."""
from __future__ import annotations

from dataclasses import dataclass, field
import random

PHASES = ("l1", "l2", "l3")
MODES = ("tri", "l1", "l2", "l3")


@dataclass
class Charger:
    index: int
    mode: str = "tri"
    starting_current: float = 16.0
    hardware_min: float = 6.0
    hardware_max: float = 32.0
    target_kwh: float = 10.0
    setpoint: float = 16.0
    actual: float = 0.0
    delivered_kwh: float = 0.0
    state: str = "idle"
    jitter: dict[str, float] = field(default_factory=lambda: dict.fromkeys(PHASES, 0.0))
    _stop_initial: float = 0.0
    _stop_remaining: float = 0.0

    @property
    def active_phases(self) -> tuple[str, ...]:
        return PHASES if self.mode == "tri" else (self.mode,)

    def start(self) -> bool:
        if self.state in ("charging", "stopping"):
            return False
        if not self.hardware_min <= self.starting_current <= self.hardware_max:
            return False
        self.setpoint = self.starting_current
        self.actual = 0.0
        self.delivered_kwh = 0.0
        self._stop_remaining = 0.0
        self.state = "charging"
        return True

    def set_current(self, value: float) -> bool:
        """Mimic a charger silently refusing an invalid limit."""
        if not self.hardware_min <= value <= self.hardware_max:
            return False
        self.setpoint = value
        return True

    def stop(self) -> None:
        if self.state == "charging":
            self.state = "stopping"
            self._stop_initial = self.actual
            self._stop_remaining = 2.0

    def current(self) -> dict[str, float]:
        return {p: (round(max(0.0, self.actual + self.jitter[p]), 3)
                    if self.actual > 0 and p in self.active_phases else 0.0)
                for p in PHASES}

    def tick(self, dt: float, time_factor: float, rng: random.Random) -> None:
        if dt <= 0:
            return
        if self.state == "charging":
            self.actual += min(abs(self.setpoint - self.actual), rng.uniform(1, 2) * dt) * (1 if self.setpoint > self.actual else -1)
        elif self.state == "stopping":
            self._stop_remaining = max(0.0, self._stop_remaining - dt)
            self.actual = self._stop_initial * self._stop_remaining / 2.0
            if self._stop_remaining <= 0:
                self.actual = 0.0
                self.state = "complete" if self.delivered_kwh >= self.target_kwh else "idle"
        else:
            self.actual = 0.0
        self.jitter = {p: rng.uniform(-0.2, 0.2) for p in PHASES}
        if self.state == "charging":
            self.delivered_kwh = min(self.target_kwh, self.delivered_kwh +
                                     (230 * sum(self.current().values()) * dt * time_factor / 3_600_000))
            if self.delivered_kwh >= self.target_kwh:
                self.stop()


@dataclass
class Parking:
    count: int = 10
    multiplier: float = 5.0
    limits: dict[str, float] = field(default_factory=lambda: dict.fromkeys(PHASES, 50.0))
    trip_delay: float = 15.0
    seed: int = 12345
    chargers: list[Charger] = field(init=False)
    overload_elapsed: float = 0.0
    tripped: bool = False
    elapsed: float = 0.0
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self):
        if not 1 <= self.count <= 100:
            raise ValueError("count must be between 1 and 100")
        if self.multiplier <= 0 or self.trip_delay <= 0:
            raise ValueError("multiplier and trip_delay must be positive")
        self.chargers = [Charger(i) for i in range(1, self.count + 1)]
        self.rng = random.Random(self.seed)

    def totals(self) -> dict[str, float]:
        currents = [c.current() for c in self.chargers]
        return {p: round(sum(x[p] for x in currents), 3) for p in PHASES}

    def excess(self) -> dict[str, float]:
        totals = self.totals()
        return {p: round(max(0.0, totals[p] - self.limits[p]), 3) for p in PHASES}

    def tick(self, dt: float) -> None:
        """Advance real-time physics by dt; only energy is accelerated."""
        if dt <= 0:
            return
        self.elapsed += dt
        if self.tripped:
            for c in self.chargers:
                c.tick(dt, self.multiplier, self.rng)
            return
        for c in self.chargers:
            c.tick(dt, self.multiplier, self.rng)
        if any(x > 0 for x in self.excess().values()):
            self.overload_elapsed += dt
            if self.overload_elapsed >= self.trip_delay:
                self.tripped = True
                for c in self.chargers:
                    c.stop()
        else:
            self.overload_elapsed = 0.0

    def reset_trip(self) -> None:
        self.tripped = False
        self.overload_elapsed = 0.0

    def randomize(self, *, minimum_kwh: float = 5, maximum_kwh: float = 40) -> None:
        if minimum_kwh <= 0 or minimum_kwh > maximum_kwh:
            raise ValueError("Invalid energy range")
        for c in self.chargers:
            if c.state in ("charging", "stopping"):
                continue
            c.mode = self.rng.choice(MODES)
            c.target_kwh = round(self.rng.uniform(minimum_kwh, maximum_kwh), 2)
            c.starting_current = float(self.rng.randint(int(c.hardware_min), int(c.hardware_max)))
            c.start()

    def load_scenario(self, data: dict) -> None:
        """Apply a scenario before starting its cycles."""
        for row in data.get("chargers", []):
            i = int(row["id"])
            if not 1 <= i <= self.count:
                raise ValueError(f"Charger {i} out of range")
            c = self.chargers[i - 1]
            if c.state in ("charging", "stopping"):
                c.stop()
                # Scenario may not replace an active cycle.
                continue
            mode = row.get("mode", c.mode)
            if mode not in MODES:
                raise ValueError(f"Invalid phase mode: {mode}")
            c.mode = mode
            c.hardware_min = float(row.get("hardware_min", c.hardware_min))
            c.hardware_max = float(row.get("hardware_max", c.hardware_max))
            c.starting_current = float(row.get("starting_current", c.starting_current))
            c.target_kwh = float(row.get("target_kwh", c.target_kwh))
            if c.hardware_min > c.hardware_max or c.target_kwh <= 0:
                raise ValueError("Invalid charger limits or energy target")
            if row.get("start", False):
                c.start()
        if "limits" in data:
            self.limits = {p: float(data["limits"][p]) for p in PHASES}
        if "trip_delay" in data:
            self.trip_delay = float(data["trip_delay"])
        if "multiplier" in data:
            self.multiplier = float(data["multiplier"])
