from pytest_homeassistant_custom_component.common import load_fixture
from custom_components.wundasmart.pywundasmart import parse_syncvalues


async def test_parse_syncvalues_v2():
    data = load_fixture("syncvalues_v2.txt")
    devices = parse_syncvalues(data)
    assert devices

    sensors = [d for d in devices.values() if d["device_type"] == "SENSOR"]
    assert len(sensors) == 10

    trvs = [d for d in devices.values() if d["device_type"] == "TRV"]
    assert len(trvs) == 0

    ufh = [d for d in devices.values() if d["device_type"] == "UFH"]
    assert len(ufh) == 4

    rooms = [d for d in devices.values() if d["device_type"] == "ROOM"]
    assert len(rooms) == 11



async def test_parse_syncvalues_v4():
    data = load_fixture("syncvalues_v4.txt")
    devices = parse_syncvalues(data)
    assert devices

    sensors = [d for d in devices.values() if d["device_type"] == "SENSOR"]
    assert len(sensors) == 9

    trvs = [d for d in devices.values() if d["device_type"] == "TRV"]
    assert len(trvs) == 5

    ufh = [d for d in devices.values() if d["device_type"] == "UFH"]
    assert len(ufh) == 1

    rooms = [d for d in devices.values() if d["device_type"] == "ROOM"]
    assert len(rooms) == 9
