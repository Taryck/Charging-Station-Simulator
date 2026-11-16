"""Further behavior checks for the HACS parking simulator."""
from test_model import Parking


def test_three_phase_total_equals_sum_of_charger_sensors():
    p = Parking(count=10, seed=123, limits={"l1": 1000, "l2": 1000, "l3": 1000})
    for index, charger in enumerate(p.chargers):
        charger.mode = ("tri", "l1", "l2", "l3")[index % 4]
        charger.start()
    for _ in range(10):
        p.tick(.5)
    for phase in ("l1", "l2", "l3"):
        assert abs(p.totals()[phase] - sum(c.current()[phase] for c in p.chargers)) < .001


def test_target_and_starting_current_remain_configured_during_regulation():
    p = Parking(count=1, seed=25)
    c = p.chargers[0]
    c.starting_current = 20
    c.target_kwh = 12
    assert c.start()
    for _ in range(8):
        p.tick(.5)
    assert c.set_current(14)
    for _ in range(30):
        p.tick(.5)
    assert c.starting_current == 20
    assert c.target_kwh == 12
    assert c.setpoint == 14


def test_hardware_minimum_refusal_does_not_change_physical_target():
    p = Parking(count=1)
    c = p.chargers[0]
    c.hardware_min = 12
    c.starting_current = 18
    assert c.start()
    assert not c.set_current(11)
    assert c.setpoint == 18
    for _ in range(30):
        p.tick(.5)
    assert abs(c.actual - 18) < .001


def test_multiple_phase_excess_is_computed_independently():
    p = Parking(count=2, seed=5, limits={"l1": 10, "l2": 10, "l3": 100})
    p.chargers[0].mode = "l1"
    p.chargers[1].mode = "l2"
    for c in p.chargers:
        assert c.start()
    for _ in range(20):
        p.tick(.5)
    excess = p.excess()
    assert excess["l1"] > 0
    assert excess["l2"] > 0
    assert excess["l3"] == 0


def test_overload_timer_resets_when_current_drops_below_threshold():
    p = Parking(count=1, trip_delay=10, limits={"l1": 4, "l2": 4, "l3": 4})
    c = p.chargers[0]
    assert c.start()
    for _ in range(5):
        p.tick(1)
    assert p.overload_elapsed > 0
    c.stop()
    for _ in range(3):
        p.tick(1)
    assert p.overload_elapsed == 0
    assert not p.tripped
