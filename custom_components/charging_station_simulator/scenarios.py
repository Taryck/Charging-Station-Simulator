"""Built-in, repeatable test scenarios, usable directly through Home Assistant."""
from .model import MODES, PHASES


def generate(name: str, count: int, seed: int = 12345) -> dict:
    if name == "random":
        return {"random": True}
    configurations = []
    for i in range(1, count + 1):
        mode = "tri"
        current = 16
        target = 20
        hmin = 6
        if name == "mono_mix":
            mode = MODES[i % 4]
        if name == "overload_two_phases":
            mode = ("l1", "l2", "tri", "l1")[i % 4]
            current = 22
        if name == "wrong_minimum":
            hmin = 12 if i % 3 == 0 else 6
        if name == "short_sessions":
            target = 0.15 + (i % 3) * 0.1
        configurations.append({"id": i, "mode": mode, "starting_current": current,
                               "hardware_min": hmin, "hardware_max": 32,
                               "target_kwh": target, "start": True})
    limit = 35 if name == "overload_two_phases" else 60
    return {"chargers": configurations, "limits": dict.fromkeys(PHASES, limit),
            "trip_delay": 15, "multiplier": 5}
