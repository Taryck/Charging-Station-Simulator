"""Configuration of an entire simulated parking site."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN


def _schema(values=None):
    d = values or {}
    fields = {
        vol.Required("name", default=d.get("name", "Parking simulé")): str,
        vol.Required("count", default=d.get("count", 10)):
            vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Required("time_factor", default=d.get("time_factor", 5)):
            vol.All(vol.Coerce(float), vol.Range(min=0.1, max=1000)),
        vol.Required("trip_delay", default=d.get("trip_delay", 15)):
            vol.All(vol.Coerce(float), vol.Range(min=1, max=3600)),
        vol.Required("seed", default=d.get("seed", 12345)): vol.Coerce(int),
    }
    for phase in ("l1", "l2", "l3"):
        fields[vol.Required(f"limit_{phase}", default=d.get(f"limit_{phase}", 60))] = \
            vol.All(vol.Coerce(float), vol.Range(min=1, max=10000))
    return vol.Schema(fields)


class ChargingStationSimulatorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=user_input["name"], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ChargingStationSimulatorOptionsFlow()


class ChargingStationSimulatorOptionsFlow(config_entries.OptionsFlow):
    """Change simulator settings or explicitly synchronize with EV load manager."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["settings", "sync"])

    async def async_step_settings(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="settings", data_schema=_schema(data))

    async def async_step_sync(self, user_input=None):
        """Preview and require explicit confirmation of the test import."""
        from homeassistant.exceptions import HomeAssistantError
        from homeassistant.loader import IntegrationNotFound, async_get_integration

        from .synchronization import build_import_data, async_import_into_manager

        errors = {}
        try:
            await async_get_integration(self.hass, "ev_load_manager")
        except IntegrationNotFound:
            errors["base"] = "manager_missing"

        payload = None
        if not errors:
            try:
                payload = build_import_data(self.hass, self.config_entry)
            except HomeAssistantError:
                errors["base"] = "entities_missing"

        if user_input is not None and user_input.get("confirm") and not errors:
            try:
                await async_import_into_manager(self.hass, payload)
            except (HomeAssistantError, ValueError, KeyError):
                errors["base"] = "sync_failed"
            else:
                # Do not alter simulator settings when synchronizing.
                return self.async_create_entry(
                    title="", data=dict(self.config_entry.options)
                )

        return self.async_show_form(
            step_id="sync",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False):
                    selector.BooleanSelector(),
            }),
            errors=errors,
            description_placeholders={
                "count": str(self.config_entry.runtime_data.parking.count),
                "parking": self.config_entry.title,
            },
        )
