"""Charging command, phase mode and built-in scenario selection."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .const import SCENARIO_NAMES
from .entity import SimEntity
from .model import MODES


class ChargerCommand(SimEntity, SelectEntity):
    _attr_options = ["Charging", "Stopped", "Paused"]

    def __init__(self, runtime, charger):
        super().__init__(runtime, f"borne_{charger.index:02d}_command",
                         f"EV Sim Borne {charger.index:02d} Command", charger)
        self._attr_translation_key = "command"
        self._attr_translation_placeholders = {"index": f"{charger.index:02d}"}

    @property
    def current_option(self):
        return "Charging" if self.charger.state == "charging" else "Stopped"

    async def async_select_option(self, option):
        if option == "Charging":
            if self.runtime.parking.tripped or not self.charger.start():
                raise HomeAssistantError("Charger could not start")
        elif option in ("Stopped", "Paused"):
            self.charger.stop()
        self.runtime.update()


class ChargerMode(SimEntity, SelectEntity):
    _attr_options = list(MODES)

    def __init__(self, runtime, charger):
        super().__init__(runtime, f"borne_{charger.index:02d}_mode",
                         f"EV Sim Borne {charger.index:02d} Mode", charger)
        self._attr_translation_key = "mode"
        self._attr_translation_placeholders = {"index": f"{charger.index:02d}"}

    @property
    def current_option(self):
        return self.charger.mode

    async def async_select_option(self, option):
        if self.charger.state in ("charging", "stopping"):
            raise HomeAssistantError("Mode is locked during a charge session")
        self.charger.mode = option
        self.runtime.update()


class ScenarioSelect(SimEntity, SelectEntity):
    _attr_options = list(SCENARIO_NAMES)

    def __init__(self, runtime):
        super().__init__(runtime, "scenario", "EV Sim Scenario")
        self._attr_translation_key = "scenario"

    @property
    def current_option(self):
        return self.runtime.scenario

    async def async_select_option(self, option):
        self.runtime.scenario = option
        self.runtime.update()


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    entities = [ScenarioSelect(runtime)]
    for c in runtime.parking.chargers:
        entities.extend([ChargerCommand(runtime, c), ChargerMode(runtime, c)])
    async_add_entities(entities)
