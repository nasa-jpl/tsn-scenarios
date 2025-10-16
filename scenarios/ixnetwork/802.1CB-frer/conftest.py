from ixnetwork_restpy import BatchAdd
import pytest


@pytest.fixture(scope="module")
def topology(config, ixn):
    if config.debug.reuse_topology:
        return

    with BatchAdd(ixn):
        for i, port in enumerate(config.ports):
            vport = i + 1
            vp = ixn.Vport.add(Name=vport, Location=f"{config.chassis};1;{port}")
            t = ixn.Topology.add(Vports=vp[-1])
            t.DeviceGroup.add(Multiplier=1)
