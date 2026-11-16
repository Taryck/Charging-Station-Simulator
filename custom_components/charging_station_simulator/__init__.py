"""HACS virtual EV charger simulation. Never talks to physical hardware."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, PLATFORMS
from .model import Parking

_LOGGER = logging.getLogger(__name__)


class SimulationRuntime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        config = {**entry.data, **entry.options}
        self.parking = Parking(
            count=int(config["count"]), multiplier=float(config["time_factor"]),
            limits={p: float(config[f"limit_{p}"]) for p in ("l1", "l2", "l3")},
            trip_delay=float(config["trip_delay"]), seed=int(config["seed"]),
        )
        self.task: asyncio.Task | None = None
        self.scenario = "balanced"
        self.signal = f"{DOMAIN}_{entry.entry_id}_updated"

    def update(self):
        async_dispatcher_send(self.hass, self.signal)

    async def run(self):
        loop = asyncio.get_running_loop()
        last = loop.time()
        try:
            while True:
                await asyncio.sleep(0.5)
                now = loop.time()
                # Bound wall-clock discontinuities (suspend/resume).
                self.parking.tick(min(now - last, 2.0))
                last = now
                self.update()
        except asyncio.CancelledError:
            raise


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    runtime = SimulationRuntime(hass, entry)
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.task = hass.async_create_task(runtime.run(), f"{DOMAIN} tick")
    entry.async_on_unload(entry.add_update_listener(_entry_updated))
    return True


async def _entry_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    runtime = entry.runtime_data
    if runtime.task is not None:
        runtime.task.cancel()
        with suppress(asyncio.CancelledError):
            await runtime.task
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
