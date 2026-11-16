"""Virtual meter and charger telemetry, updated from the same model."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass

from .entity import SimEntity
from .model import PHASES


class CurrentSensor(SimEntity, SensorEntity):
    _attr_native_unit_of_measurement = "A"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime, phase, charger=None):
        self.phase = phase
        self._translation_category = "total_current" if charger is None else "charger_current"
        suffix = f"total_{phase}" if charger is None else f"borne_{charger.index:02d}_{phase}"
        label = f"EV Sim Total {phase.upper()}" if charger is None else f"EV Sim Borne {charger.index:02d} {phase.upper()}"
        super().__init__(runtime, suffix, label, charger)
        self._attr_translation_key = self._translation_category
        self._attr_translation_placeholders = {"phase": phase.upper(), "index": f"{charger.index:02d}" if charger else ""}

    @property
    def native_value(self):
        if self.charger is None:
            return self.runtime.parking.totals()[self.phase]
        return self.charger.current()[self.phase]


class EnergySensor(SimEntity, SensorEntity):
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, runtime, charger):
        super().__init__(runtime, f"borne_{charger.index:02d}_energy",
                         f"EV Sim Borne {charger.index:02d} Energy", charger)
        self._attr_translation_key = "energy"
        self._attr_translation_placeholders = {"index": f"{charger.index:02d}"}

    @property
    def native_value(self):
        return round(self.charger.delivered_kwh, 5)


class StatusSensor(SimEntity, SensorEntity):
    def __init__(self, runtime, charger):
        super().__init__(runtime, f"borne_{charger.index:02d}_status",
                         f"EV Sim Borne {charger.index:02d} Status", charger)
        self._attr_translation_key = "charger_status"
        self._attr_translation_placeholders = {"index": f"{charger.index:02d}"}

    @property
    def native_value(self):
        return self.charger.state

    @property
    def extra_state_attributes(self):
        c = self.charger
        return {"mode": c.mode, "initial_current_a": c.starting_current,
                "session_initial_current_a": c.starting_current if c.state != "idle" else None,
                "setpoint_a": c.setpoint, "physical_current_a": round(c.actual, 3),
                "hardware_min_a": c.hardware_min, "hardware_max_a": c.hardware_max,
                "target_kwh": c.target_kwh, "delivered_kwh": round(c.delivered_kwh, 4)}


class ParkingStatus(SimEntity, SensorEntity):
    def __init__(self, runtime):
        super().__init__(runtime, "parking_status", "EV Sim Parking Status")
        self._attr_translation_key = "parking_status"

    @property
    def native_value(self):
        return "tripped" if self.runtime.parking.tripped else "running"

    @property
    def extra_state_attributes(self):
        p = self.runtime.parking
        return {"chargers": p.count, "time_factor": p.multiplier,
                "trip_delay_s": p.trip_delay, "overload_elapsed_s": round(p.overload_elapsed, 2),
                "limits_a": p.limits.copy(), "totals_a": p.totals(),
                "excess_a": p.excess(), "elapsed_real_s": round(p.elapsed, 1)}


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    entities = [ParkingStatus(runtime)]
    entities += [CurrentSensor(runtime, phase) for phase in PHASES]
    for c in runtime.parking.chargers:
        entities += [CurrentSensor(runtime, phase, c) for phase in PHASES]
        entities += [EnergySensor(runtime, c), StatusSensor(runtime, c)]
    async_add_entities(entities)
