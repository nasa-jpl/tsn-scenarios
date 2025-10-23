import logging

from ixnetwork_restpy import BatchAdd
import pytest

from ixnetwork_restpy_helpers import run_traffic_blocking, StatsViewSnapshot

CTAG_SIZE = 4
RTAG_SIZE = 6

FRAME_COUNT = 10
FRAME_SIZE = 64
FRAME_SIZE_REPLICATED = FRAME_SIZE + CTAG_SIZE + RTAG_SIZE
FRAME_SIZE_NONREPLICATED = FRAME_SIZE

ADDR_NONFRER_TALKER = "02:00:00:00:00:01"
ADDR_FRER_LISTENER = "02:00:00:00:00:02"
ADDR_NONFRER_LISTENER = "02:00:00:00:00:03"

logger = logging.getLogger(__name__)


@pytest.fixture
def add_traffic(ixn):
    """
    Generate a simple L2 quick flow traffic item.

    Uses the "factory as fixture" pattern [1] to allow the test to pass
    arguments (e.g., src_addr) to the fixture.

    [1]: https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures
    """

    def _add_traffic(name, src_addr, dst_addr):
        logger.info("Creating traffic")
        with BatchAdd(ixn):
            traffic = ixn.Traffic.TrafficItem.add(
                Name=name,
                TrafficType="raw",
                TrafficItemType="quick",
            )
            vport = ixn.Vport.find()[0]
            traffic.EndpointSet.add(Sources=vport.Protocols.find())
            stream = traffic.HighLevelStream.add(TxPortId=vport)
            stream.FrameSize.FixedSize = FRAME_SIZE
            stream.TransmissionControl.Type = "fixedFrameCount"
            stream.TransmissionControl.FrameCount = FRAME_COUNT
            stack = stream.Stack.add()
            eth = stack.Ethernet.add()
            eth.SourceAddress.Single(src_addr)
            eth.DestinationAddress.Single(dst_addr)

        traffic.Generate()
        ixn.Traffic.Apply()
        ixn.ClearStats()

        return

    logger.info("Removing traffic")
    ixn.Traffic.TrafficItem.find().remove()

    return _add_traffic


def test_replication(switch, ixn, vports, add_traffic):
    """
    Send N frames on port 0.

    Verify that they are replicated to both ports 1 and 2 and that both VLAN
    tag and R-Tag have been added.
    """
    add_traffic(
        name="Replication", src_addr=ADDR_NONFRER_TALKER, dst_addr=ADDR_FRER_LISTENER
    )

    run_traffic_blocking(ixn)

    ports = StatsViewSnapshot(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_REPLICATED
    assert ports[2]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[2]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_REPLICATED


def test_no_replication(switch, ixn, vports, add_traffic):
    """
    Send traffic on port 0.

    Verify that it is only forwarded to port 1 w/o modification.
    """
    add_traffic(
        name="No replication",
        src_addr=ADDR_NONFRER_TALKER,
        dst_addr=ADDR_NONFRER_LISTENER,
    )

    run_traffic_blocking(ixn)

    ports = StatsViewSnapshot(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_NONREPLICATED
    assert ports[2]["Valid Frames Rx."] == 0
    assert ports[2]["Bytes Rx."] == 0
