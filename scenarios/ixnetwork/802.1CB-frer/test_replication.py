import time

import pytest

from ixnetwork_restpy_helpers import StatsViewSnapshot

RTAG_ETHER_TYPE = "f1c1"
NOVLAN_ETHER_TYPE_BYTE_OFFSET = 12
VLAN_ETHER_TYPE_BYTE_OFFSET = 16
CTAG_SIZE = 4
RTAG_SIZE = 6

FRAME_COUNT = 10
FRAME_SIZE = 64
FRAME_SIZE_REPLICATED = FRAME_SIZE + CTAG_SIZE + RTAG_SIZE
FRAME_SIZE_NONREPLICATED = FRAME_SIZE

ADDR_NONFRER_TALKER = "02:00:00:00:00:01"
ADDR_FRER_LISTENER = "02:00:00:00:00:02"
ADDR_NONFRER_LISTENER = "02:00:00:00:00:03"


@pytest.fixture
def add_traffic(ixn):
    """
    Generate a simple L2 quick flow traffic item.

    Uses the "factory as fixture" pattern [1] to allow the test to pass
    arguments (e.g., src_addr) to the fixture.

    [1]: https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures
    """

    def _add_traffic(name, src_addr, dst_addr):
        traffic_item = ixn.Traffic.TrafficItem.add(
            Name=name,
            TrafficType="raw",
            TrafficItemType="quick",
        )
        vport = ixn.Vport.find()[0]
        traffic_item.EndpointSet.add(Sources=vport.Protocols.find())

        stream = traffic_item.HighLevelStream.find()
        stream.FrameSize.update(
            Type="fixed",
            FixedSize=FRAME_SIZE,
        )
        stream.TransmissionControl.update(
            Type="fixedFrameCount",
            FrameCount=FRAME_COUNT,
        )

        ethernet_stack = stream.Stack.find(StackTypeId="^ethernet$")
        ethernet_stack.Field.find(Name="sourceAddress").SingleValue = src_addr
        ethernet_stack.Field.find(Name="destinationAddress").SingleValue = dst_addr

        ixn.Traffic.Apply()

        return traffic_item

    yield _add_traffic

    # Prevent cleanup on failure so that we can inspect the state of the system
    if not pytest.any_test_failed:
        ixn.Traffic.TrafficItem.find().remove()
        ixn.ClearStats()


def test_replication(ixn, topology, add_traffic):
    """
    Send N frames on port 0.

    Verify that they are replicated to both ports 1 and 2 and that both VLAN
    tag and R-Tag have been added.
    """
    traffic = add_traffic(
        name="Replication", src_addr=ADDR_NONFRER_TALKER, dst_addr=ADDR_FRER_LISTENER
    )

    traffic.StartStatelessTrafficBlocking()
    # FIXME: Poll "Frames Tx." stat instead?
    time.sleep(5)
    traffic.StopStatelessTrafficBlocking()

    ports = StatsViewSnapshot(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_REPLICATED
    assert ports[2]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[2]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_REPLICATED


def test_no_replication(ixn, topology, add_traffic):
    """
    Send traffic on port 0.

    Verify that it is only forwarded to port 1 w/o modification.
    """
    traffic = add_traffic(
        name="No replication",
        src_addr=ADDR_NONFRER_TALKER,
        dst_addr=ADDR_NONFRER_LISTENER,
    )

    traffic.StartStatelessTrafficBlocking()
    # FIXME: Poll "Frames Tx." stat instead?
    time.sleep(5)
    traffic.StopStatelessTrafficBlocking()

    ports = StatsViewSnapshot(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_NONREPLICATED
    assert ports[2]["Valid Frames Rx."] == 0
    assert ports[2]["Bytes Rx."] == 0
