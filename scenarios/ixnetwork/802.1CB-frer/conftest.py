from ixnetwork_restpy import BatchAdd
import pytest


@pytest.fixture(scope="module")
def topology(config, ixn):
    if config.debug.reuse_topology:
        return

    with BatchAdd(ixn):
        for i, port in enumerate(config.ports):
            ixn.Vport.add(Name=i, Location=f"{config.chassis};1;{port}")
