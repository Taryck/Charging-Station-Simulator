"""Common HA entity base for simulator entities."""
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.core import callback


class SimEntity:
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime, suffix: str, label: str, charger=None):
        self.runtime = runtime
        self.charger = charger
        self._attr_unique_id = f"{runtime.entry.entry_id}_{suffix}"
        self._attr_name = None
        self._attr_suggested_object_id = f"ev_sim_{suffix}"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.runtime.signal, self._updated
        ))

    @callback
    def _updated(self):
        self.async_write_ha_state()
