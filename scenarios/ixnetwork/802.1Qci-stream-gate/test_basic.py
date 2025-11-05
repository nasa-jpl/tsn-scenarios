import logging

from ixnetwork_restpy import BatchAdd
import pytest

from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)

NATIVE_VLAN = 0
VLAN_ETHER_TYPE = "8100"
RTAG_ETHER_TYPE = "f1c1"

FRAME_COUNT = 10
FRAME_SIZE = 64
FRAMES_PER_SECOND = 1000
STREAM_START_DELAY_US = 5

ADDR_TALKER1 = "02:00:00:00:00:01"
ADDR_TALKER2 = "02:00:00:00:00:02"
ADDR_LISTENER = "02:00:00:00:00:03"
ADDRS = [
    ADDR_TALKER1,
    ADDR_TALKER2,
    ADDR_LISTENER,
]


logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def protocols(ixn, vports):
    logger.info("Adding protocols")

    ixn.Traffic.UseScheduledStartTransmit = True

    protocols = []

    with BatchAdd(ixn):
        for i, (vport, addr) in enumerate(zip(vports, ADDRS)):
            topology = ixn.Topology.add(Vports=vport)
            dg = topology.DeviceGroup.add(Multiplier=1)

            eth = dg.Ethernet.add()
            eth.Mac.Single(addr)
            ptp = eth.Ptp.add()
            if i == 0:
                ptp.Role.Single("master")
            ptp.Profile.Single("ieee8021asrev")

            eth = dg.Ethernet.add()
            eth.Mac.Single(addr)
            eth.EnableVlans.Single(True)
            eth.VlanCount = 1
            vlan = eth.Vlan.add()
            vlan.VlanId.Single(0)

            protocols.append(eth[-1])

    return protocols


@pytest.fixture
def add_traffic(ixn):
    """
    Generate a simple L2 quick flow traffic item.

    Uses the "factory as fixture" pattern [1] to allow the test to pass
    arguments (e.g., src_addr) to the fixture.

    [1]: https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures
    """

    def _add_traffic(name, src_proto, dst_proto, start_delay_us):
        with BatchAdd(ixn):
            traffic = ixn.Traffic.TrafficItem.add(
                Name=name,
                TrafficType="ethernetVlan",
                TrafficItemType="l2L3",
            )
            traffic.EndpointSet.add(
                Sources=src_proto,
                Destinations=dst_proto,
            )
            stream = traffic.ConfigElement.add()

            stream.FrameSize.FixedSize = 64
            stream.FrameRate.Type = "framesPerSecond"
            stream.FrameRate.Rate = FRAMES_PER_SECOND
            stream.TransmissionControl.StartDelayUnits = "microseconds"
            stream.TransmissionControl.StartDelay = start_delay_us

            traffic.Tracking.add(TrackBy=["trackingenabled0"])

        return

    ixn.Traffic.TrafficItem.find().remove()
    logger.info("Creating traffic")

    return _add_traffic


def test_drop(switch, ixn, vports, protocols, add_traffic):
    add_traffic(
        name="Stream 1",
        src_proto=protocols[0],
        dst_proto=protocols[-1],
        start_delay_us=5,
    )
    add_traffic(
        name="Stream 2",
        src_proto=protocols[1],
        dst_proto=protocols[-1],
        start_delay_us=5,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=0)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=0)


def test_forward(switch, ixn, vports, protocols, add_traffic):
    add_traffic(
        name="Stream 1",
        src_proto=protocols[0],
        dst_proto=protocols[-1],
        start_delay_us=255,
    )
    add_traffic(
        name="Stream 2",
        src_proto=protocols[1],
        dst_proto=protocols[-1],
        start_delay_us=505,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=1000)
