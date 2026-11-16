"""Writable numbers simulate charger settings, not physical currents."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError

from .entity import SimEntity


class ChargerNumber(SimEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, runtime, charger, field):
        self.field = field
        label = {"setpoint": "Current", "starting_current": "Starting current",
                 "hardware_min": "Hardware minimum", "hardware_max": "Hardware maximum",
                 "target_kwh": "Target energy"}[field]
        super().__init__(runtime, f"borne_{charger.index:02d}_{field}",
                         f"EV Sim Borne {charger.index:02d} {label}", charger)
        self._attr_translation_key = field
        self._attr_translation_placeholders = {"index": f"{charger.index:02d}"}
        self._attr_native_unit_of_measurement = "kWh" if field == "target_kwh" else "A"
        self._attr_native_min_value = 0.01 if field == "target_kwh" else 0.0
        self._attr_native_max_value = 500 if field == "target_kwh" else 100.0
        self._attr_native_step = 0.01 if field == "target_kwh" else 1.0

    @property
    def native_value(self):
        return getattr(self.charger, self.field)

    async def async_set_native_value(self, value):
        c = self.charger
        if self.field == "setpoint":
            if not c.set_current(value):
                raise HomeAssistantError("Charger rejected setpoint outside hardware limits")
        elif self.field == "starting_current":
            if c.state in ("charging", "stopping"):
                raise HomeAssistantError("Starting current is immutable during a session")
            if not c.hardware_min <= value <= c.hardware_max:
                raise HomeAssistantError("Starting current outside hardware limits")
            c.starting_current = value
        elif self.field in ("hardware_min", "hardware_max"):
            if c.state in ("charging", "stopping"):
                raise HomeAssistantError("Hardware limits are locked during a session")
            if self.field == "hardware_min" and value > c.hardware_max:
                raise HomeAssistantError("Minimum greater than maximum")
            if self.field == "hardware_max" and value < c.hardware_min:
                raise HomeAssistantError("Maximum lower than minimum")
            setattr(c, self.field, value)
        elif self.field == "target_kwh":
            if c.state in ("charging", "stopping"):
                raise HomeAssistantError("Target energy is locked during a session")
            c.target_kwh = value
        self.runtime.update()


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    fields = ("setpoint", "starting_current", "hardware_min", "hardware_max", "target_kwh")
    async_add_entities([ChargerNumber(runtime, c, f) for c in runtime.parking.chargers for f in fields])
