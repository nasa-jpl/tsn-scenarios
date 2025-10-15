from ixnetwork_restpy import BatchAdd
import pytest

@pytest.fixture(scope="module")
def topology(config, ixn):
    chassis = config["chassis"]
    ports = config["ports"]

    with BatchAdd(ixn):
        for i, port in enumerate(ports):
            vport = i + 1
            vp = ixn.Vport.add(Name=vport, Location=f"{chassis};1;{port}")
            t = ixn.Topology.add(Vports=vp[-1])
            t.DeviceGroup.add(Multiplier=1)
