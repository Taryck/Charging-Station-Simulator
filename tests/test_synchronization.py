"""Unit tests for opt-in simulator to EV-load-manager synchronization.

No Home Assistant installation is needed; the entity registry and flow are
small fakes. These tests never write to a physical configuration entry.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


def load_adapter(monkeypatch):
    ha = ModuleType("homeassistant")
    errors = ModuleType("homeassistant.exceptions")
    registry = ModuleType("homeassistant.helpers.entity_registry")
    helpers = ModuleType("homeassistant.helpers")

    class HomeAssistantError(Exception):
        pass

    errors.HomeAssistantError = HomeAssistantError
    helpers.entity_registry = registry
    ha.exceptions = errors
    ha.helpers = helpers

    for name, mod in (
        ("homeassistant", ha),
        ("homeassistant.exceptions", errors),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.entity_registry", registry),
    ):
        monkeypatch.setitem(sys.modules, name, mod)

    path = Path(__file__).resolve().parents[1] / "custom_components" / "charging_station_simulator" / "synchronization.py"
    spec = importlib.util.spec_from_file_location("ev_sim_sync_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, registry, HomeAssistantError


def make_environment(registry, count=10):
    entry_id = "test-parking-123"
    mapping = {}
    for phase in ("l1", "l2", "l3"):
        mapping[("sensor", "charging_station_simulator",
                 f"{entry_id}_total_{phase}")] = f"sensor.renamed_meter_{phase}"
    chargers = []
    for i in range(1, count + 1):
        suffix = f"borne_{i:02d}"
        for phase in ("l1", "l2", "l3"):
            mapping[("sensor", "charging_station_simulator",
                     f"{entry_id}_{suffix}_{phase}")] = f"sensor.renamed_{suffix}_{phase}"
        mapping[("number", "charging_station_simulator",
                 f"{entry_id}_{suffix}_setpoint")] = f"number.renamed_{suffix}_setpoint"
        mapping[("select", "charging_station_simulator",
                 f"{entry_id}_{suffix}_command")] = f"select.renamed_{suffix}_command"
        chargers.append(SimpleNamespace(index=i, hardware_min=8, hardware_max=32))

    fake_registry = SimpleNamespace(async_get_entity_id=lambda *args: mapping.get(args))
    registry.async_get = lambda hass: fake_registry
    parking = SimpleNamespace(chargers=chargers, limits={"l1": 35, "l2": 40, "l3": 50})
    entry = SimpleNamespace(
        entry_id=entry_id,
        title="Parking de test",
        runtime_data=SimpleNamespace(parking=parking),
    )
    return entry, mapping


def test_payload_uses_registered_entities_and_has_ten_chargers(monkeypatch):
    module, registry, _ = load_adapter(monkeypatch)
    entry, _ = make_environment(registry)
    payload = module.build_import_data(object(), entry)
    assert payload["origin"] == "charging_station_simulator"
    assert payload["current_l1"] == "sensor.renamed_meter_l1"
    assert payload["max_l3"] == 50
    assert len(payload["simulator_chargers"]) == 10
    c = payload["simulator_chargers"][0]
    assert c["current_l2"] == "sensor.renamed_borne_01_l2"
    assert c["setpoint"] == "number.renamed_borne_01_setpoint"
    assert c["control_entity"] == "select.renamed_borne_01_command"
    assert c["start_value"] == "Charging"
    assert c["stop_value"] == "Stopped"
    assert c["simulator_key"].endswith(":01")


def test_stable_keys_allow_repeated_synchronization_without_duplicates(monkeypatch):
    module, registry, _ = load_adapter(monkeypatch)
    entry, _ = make_environment(registry, 4)
    one = module.build_import_data(object(), entry)
    two = module.build_import_data(object(), entry)
    assert [c["simulator_key"] for c in one["simulator_chargers"]] == [
        c["simulator_key"] for c in two["simulator_chargers"]
    ]


def test_missing_registry_entity_prevents_partial_import(monkeypatch):
    module, registry, error = load_adapter(monkeypatch)
    entry, mapping = make_environment(registry, 2)
    mapping.pop(("number", "charging_station_simulator", f"{entry.entry_id}_borne_02_setpoint"))
    with pytest.raises(error):
        module.build_import_data(object(), entry)


@pytest.mark.asyncio
async def test_manager_flow_creation_and_update_are_accepted(monkeypatch):
    module, registry, _ = load_adapter(monkeypatch)
    for response in (
        {"type": "create_entry"},
        {"type": "abort", "reason": "already_configured"},
    ):
        calls = []

        async def async_init(domain, context, data):
            calls.append((domain, context, data))
            return response

        hass = SimpleNamespace(config_entries=SimpleNamespace(
            flow=SimpleNamespace(async_init=async_init)
        ))
        await module.async_import_into_manager(hass, {"test": 1})
        assert calls == [("ev_load_manager", {"source": "import"}, {"test": 1})]


@pytest.mark.asyncio
async def test_manager_rejected_import_is_not_reported_as_success(monkeypatch):
    module, _, error = load_adapter(monkeypatch)

    async def async_init(domain, context, data):
        return {"type": "abort", "reason": "invalid_import"}

    hass = SimpleNamespace(config_entries=SimpleNamespace(
        flow=SimpleNamespace(async_init=async_init)
    ))
    with pytest.raises(error):
        await module.async_import_into_manager(hass, {"test": 1})
