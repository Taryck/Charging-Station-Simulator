"""Safely prepare an EV Load Manager installation from a simulated parking.

Only registry entities belonging to THIS simulator config entry are used. The
manager import flow owns creation and reconciliation of its configuration.
No physical or manually configured installation can be selected or overwritten.
"""
from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

SIMULATOR_DOMAIN = "charging_station_simulator"
MANAGER_DOMAIN = "ev_load_manager"
PHASES = ("l1", "l2", "l3")


def _entity_id(registry, simulator_entry_id: str, domain: str, suffix: str) -> str:
    """Find actual registered ID, including custom user renames."""
    unique_id = f"{simulator_entry_id}_{suffix}"
    entity_id = registry.async_get_entity_id(domain, SIMULATOR_DOMAIN, unique_id)
    if entity_id is None:
        raise HomeAssistantError(
            f"Simulator entity missing from registry: {domain} / {unique_id}"
        )
    return entity_id


def build_import_data(hass, entry) -> dict:
    """Translate simulated entities into the manager's config-entry schema."""
    registry = er.async_get(hass)
    parking = entry.runtime_data.parking
    data = {
        "origin": SIMULATOR_DOMAIN,
        "simulator_entry_id": entry.entry_id,
        "simulator_name": entry.title,
        "simulator_chargers": [],
    }
    for phase in PHASES:
        data[f"current_{phase}"] = _entity_id(
            registry, entry.entry_id, "sensor", f"total_{phase}"
        )
        data[f"max_{phase}"] = float(parking.limits[phase])

    for charger in parking.chargers:
        suffix = f"borne_{charger.index:02d}"
        charger_data = {
            "simulator_key": f"{SIMULATOR_DOMAIN}:{entry.entry_id}:{charger.index:02d}",
            "name": f"{entry.title} - Borne {charger.index:02d}",
            "setpoint": _entity_id(
                registry, entry.entry_id, "number", f"{suffix}_setpoint"
            ),
            "control_entity": _entity_id(
                registry, entry.entry_id, "select", f"{suffix}_command"
            ),
            "start_value": "Charging",
            "stop_value": "Stopped",
            "min_current": float(charger.hardware_min),
            "max_current": float(charger.hardware_max),
        }
        for phase in PHASES:
            charger_data[f"current_{phase}"] = _entity_id(
                registry, entry.entry_id, "sensor", f"{suffix}_{phase}"
            )
        data["simulator_chargers"].append(charger_data)
    return data


async def async_import_into_manager(hass, payload: dict) -> None:
    """Invoke manager's documented config flow instead of editing .storage."""
    result = await hass.config_entries.flow.async_init(
        MANAGER_DOMAIN,
        context={"source": "import"},
        data=payload,
    )
    result_type = result.get("type")
    # A successful update returns 'abort: already_configured'; initial
    # creation returns 'create_entry'. Other abort reasons are failures.
    if str(result_type) not in (
        "create_entry", "abort",
        "FlowResultType.CREATE_ENTRY", "FlowResultType.ABORT",
    ):
        raise HomeAssistantError(f"Unexpected manager import response: {result_type}")
    if str(result_type) in ("abort", "FlowResultType.ABORT") and result.get("reason") != "already_configured":
        raise HomeAssistantError(
            f"EV load manager did not accept the import: {result.get('reason')}"
        )
