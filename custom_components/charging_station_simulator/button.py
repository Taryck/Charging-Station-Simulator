"""Start/stop individual charging sessions and exercise scenarios."""
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import SimEntity
from .scenarios import generate


class ChargerStart(SimEntity, ButtonEntity):
    def __init__(self, runtime, charger):
        super().__init__(runtime, f"borne_{charger.index:02d}_start",
                         f"EV Sim Borne {charger.index:02d} Start", charger)
        self._attr_translation_key = "start"
        self._attr_translation_placeholders = {"index": f"{charger.index:02d}"}

    async def async_press(self):
        if self.runtime.parking.tripped or not self.charger.start():
            raise HomeAssistantError("Cannot start charging")
        self.runtime.update()


class ParkingAction(SimEntity, ButtonEntity):
    def __init__(self, runtime, action):
        self.action = action
        super().__init__(runtime, f"parking_{action}", f"EV Sim Parking {action.replace('_', ' ').title()}")
        self._attr_translation_key = action

    async def async_press(self):
        parking = self.runtime.parking
        if self.action == "reset_trip":
            parking.reset_trip()
        elif self.action == "stop_all":
            for c in parking.chargers:
                c.stop()
        elif self.action == "start_all":
            if parking.tripped:
                raise HomeAssistantError("Parking circuit breaker is tripped")
            for c in parking.chargers:
                c.start()
        elif self.action == "load_scenario":
            if parking.tripped:
                raise HomeAssistantError("Reset trip before starting a new scenario")
            if any(c.state in ("charging", "stopping") for c in parking.chargers):
                raise HomeAssistantError("Stop all sessions before loading another scenario")
            scenario = generate(self.runtime.scenario, parking.count, parking.seed)
            if scenario.get("random"):
                parking.randomize()
            else:
                parking.load_scenario(scenario)
        self.runtime.update()


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    entities = [ParkingAction(runtime, action) for action in
                ("start_all", "stop_all", "reset_trip", "load_scenario")]
    entities.extend(ChargerStart(runtime, c) for c in runtime.parking.chargers)
    async_add_entities(entities)
