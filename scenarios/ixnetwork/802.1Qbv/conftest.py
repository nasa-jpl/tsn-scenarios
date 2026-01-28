import logging

from ixnetwork_restpy import BatchAdd
import pytest


logger = logging.getLogger(__name__)

FRAME_SIZE = 64
FRAMES_PER_SECOND = 1000

VLAN_ETHER_TYPE = "8100"
ADDR_TALKER1 = "02:00:00:00:00:01"
ADDR_TALKER2 = "02:00:00:00:00:02"
ADDR_LISTENER = "02:00:00:00:00:03"
ADDRS = [
    ADDR_TALKER1,
    ADDR_TALKER2,
    ADDR_LISTENER,
]


@pytest.fixture
def add_traffic(ixn, vports):
    """
    Generate a simple L2 quick flow traffic item.

    Uses the "factory as fixture" pattern [1] to allow the test to pass
    arguments (e.g., src_addr) to the fixture.

    [1]: https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures
    """

    def _add_traffic(
        name: str,
        src_idx: int,
        dst_idx: int,
        pcp: int = 0,
        start_delay_us: int = 0,
    ):
        with BatchAdd(ixn):
            traffic = ixn.Traffic.TrafficItem.add(
                Name=name,
                TrafficType="raw",
                TrafficItemType="l2L3",
            )
            traffic.EndpointSet.add(
                Sources=vports[src_idx].Protocols.find(),
                Destinations=vports[dst_idx].Protocols.find(),
            )
            stream = traffic.ConfigElement.add()

            stream.FrameSize.Type = "fixed"
            stream.FrameSize.FixedSize = FRAME_SIZE
            stream.FrameRate.Type = "framesPerSecond"
            stream.FrameRate.Rate = FRAMES_PER_SECOND
            stream.TransmissionControl.StartDelayUnits = "microseconds"
            stream.TransmissionControl.StartDelay = start_delay_us

            stack = stream.Stack.add()
            eth = stack.Ethernet.add()
            eth.SourceAddress.Single(ADDRS[src_idx])
            eth.DestinationAddress.Single(ADDRS[dst_idx])
            eth.EtherType.Single(VLAN_ETHER_TYPE)
            vlan = stack.Vlan.add()
            vlan.VlanTagVlanID.Single(3)
            vlan.VlanTagVlanUserPriority.Single(pcp)

            traffic.Tracking.add(TrackBy=["trackingenabled0"])

        return

    ixn.Traffic.TrafficItem.find().remove()
    logger.info("Creating traffic")

    return _add_traffic


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

            protocols.append(eth)

    return protocols
