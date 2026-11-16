"""Pure simulation tests; pytest runs without Home Assistant."""
import importlib.util
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1] / 'custom_components' / 'charging_station_simulator'
spec = importlib.util.spec_from_file_location('ev_sim_model', root / 'model.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Charger, Parking = module.Charger, module.Parking


def test_only_chargers_are_in_totals():
    p = Parking(count=3)
    assert p.totals() == {'l1': 0, 'l2': 0, 'l3': 0}
    p.chargers[0].mode = 'l2'
    p.chargers[0].start()
    for _ in range(40): p.tick(0.5)
    assert p.totals()['l1'] == 0 and p.totals()['l3'] == 0
    assert 15.8 <= p.totals()['l2'] <= 16.2


def test_three_phase_jitter_is_independent():
    p = Parking(count=1, seed=41)
    p.chargers[0].start()
    for _ in range(30): p.tick(.5)
    currents = p.chargers[0].current()
    assert len(set(currents.values())) == 3
    assert all(abs(v - p.chargers[0].actual) <= .2 for v in currents.values())


def test_setpoint_ramps_not_jump_and_start_current_stays():
    p = Parking(count=1)
    c = p.chargers[0]
    c.start()
    p.tick(1)
    assert 1 <= c.actual <= 2
    assert c.set_current(8)
    for _ in range(12): p.tick(1)
    assert c.starting_current == 16 and c.setpoint == 8
    assert abs(c.actual - 8) <= 0.001


def test_hardware_minimum_refuses_invalid_request():
    p = Parking(count=1)
    c = p.chargers[0]
    c.hardware_min = 12
    c.start()
    assert not c.set_current(10)
    assert c.setpoint == 16


def test_stop_takes_two_real_seconds_even_with_factor_20():
    p = Parking(count=1, multiplier=20)
    c = p.chargers[0]
    c.start()
    for _ in range(20): p.tick(.5)
    c.stop()
    before = c.actual
    p.tick(1)
    assert abs(c.actual - before/2) < 0.001
    p.tick(1)
    assert c.actual == 0 and all(v == 0 for v in c.current().values())


def test_energy_multiplier_does_not_accelerate_ramping():
    a, b = Parking(count=1, multiplier=1), Parking(count=1, multiplier=20)
    a.chargers[0].start(); b.chargers[0].start()
    for _ in range(10):
        a.tick(.5); b.tick(.5)
    assert a.chargers[0].actual == b.chargers[0].actual
    assert abs(b.chargers[0].delivered_kwh/a.chargers[0].delivered_kwh - 20) < .0001


def test_end_of_energy_stops_and_reaches_zero_after_two_seconds():
    p = Parking(count=1, multiplier=50)
    c = p.chargers[0]
    c.target_kwh = .001
    c.start()
    for _ in range(30): p.tick(.5)
    assert c.state == 'complete' and c.actual == 0
    assert c.delivered_kwh == .001


def test_trip_requires_continuous_overload_and_can_reset():
    p = Parking(count=1, trip_delay=3, limits={'l1': 1, 'l2': 1, 'l3': 1})
    p.chargers[0].start()
    for _ in range(3): p.tick(1)
    assert p.tripped
    for _ in range(3): p.tick(1)
    assert p.totals() == {'l1': 0, 'l2': 0, 'l3': 0}
    p.reset_trip()
    assert not p.tripped


def test_scenario_changes_all_count_without_house_load():
    p = Parking(count=10)
    p.load_scenario({'chargers': [
        {'id': i, 'mode': ('tri' if i % 2 else 'l1'),
         'starting_current': 10 + i, 'target_kwh': 1, 'start': True}
        for i in range(1, 11)]})
    assert len(p.chargers) == 10
    assert len([c for c in p.chargers if c.state == 'charging']) == 10


def test_seeded_random_session_is_reproducible():
    a, b = Parking(count=8, seed=77), Parking(count=8, seed=77)
    a.randomize(); b.randomize()
    assert [(c.mode, c.starting_current, c.target_kwh) for c in a.chargers] == \
           [(c.mode, c.starting_current, c.target_kwh) for c in b.chargers]


def test_bulk_random_targets_do_not_restart_or_change_active_sessions():
    p = Parking(count=4, seed=7)
    p.chargers[0].start()
    p.tick(1)
    old_target = p.chargers[0].target_kwh
    old_energy = p.chargers[0].delivered_kwh
    p.randomize_targets(minimum_kwh=20, maximum_kwh=30)
    assert p.chargers[0].target_kwh == old_target
    assert p.chargers[0].delivered_kwh == old_energy
    assert all(20 <= c.target_kwh <= 30 for c in p.chargers[1:])
    assert all(c.state == "idle" for c in p.chargers[1:])


def test_taper_spans_simulated_twenty_minutes_and_respects_minimum():
    p = Parking(count=1, multiplier=20, limits=dict.fromkeys(("l1", "l2", "l3"), 100))
    c = p.chargers[0]
    c.hardware_min = 7
    c.target_kwh = 2
    assert c.start()
    currents = []
    for _ in range(500):
        p.tick(.5)
        if c.tapering:
            currents.append(c.actual)
        if c.state == "complete":
            break
    assert currents
    assert max(currents) > min(currents) + 3
    assert c.delivered_kwh == c.target_kwh
    assert c.state == "complete"
    assert c._taper_elapsed >= 60  # Accelerated simulated time, not wall time.


def test_external_setpoint_is_not_rewritten_by_battery_taper():
    p = Parking(count=1, multiplier=10, limits=dict.fromkeys(("l1", "l2", "l3"), 100))
    c = p.chargers[0]
    c.hardware_min = 12
    c.target_kwh = 1
    c.start()
    for _ in range(30):
        p.tick(.5)
    assert c.tapering
    assert c.setpoint == 16
    assert c._taper_current(1200) == 12
