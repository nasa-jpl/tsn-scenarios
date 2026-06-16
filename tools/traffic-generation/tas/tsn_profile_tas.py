from trex_stl_lib.api import (
    STLProfile,
    STLStream,
    STLTXCont,
    STLPktBuilder,
    STLFlowLatencyStats,
)
from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP


class STLTsnTasProfile(object):
    """TSN traffic profile with latency measurement for 802.1Qbv TAS experiment.

    TAS gate schedule on the switch egress port (1 ms cycle):
      Window 0 [  0 - 500 us]: queues 2, 7 open
      Window 1 [500 - 1000 us]: queues 3, 7 open

    Uses continuous streams with STLFlowLatencyStats to measure how TAS
    gates affect per-stream latency.  Streams that hit a closed gate will
    be queued in the switch, adding measurable delay vs the always-open
    queue 7 baseline.
    """

    def __init__(self):
        pass

    def get_streams(self, direction=0, **kwargs):
        vlan_id = kwargs.get("vlan_id", 3)
        pps = kwargs.get("pps", 25000)
        bg_pps = kwargs.get("bg_pps", 1000)

        streams = []

        # --- Queue 2 traffic (PCP 2) - open during window 0 [0-500 us] ---
        pkt_q2 = (
            Ether(dst="02:00:00:00:00:03")
            / Dot1Q(vlan=vlan_id, prio=2)
            / IP(src="10.0.0.2", dst="10.0.1.1")
            / UDP(sport=5002, dport=5002)
            / (b"\x00" * 256)
        )

        streams.append(STLStream(
            name="q2",
            packet=STLPktBuilder(pkt=pkt_q2),
            mode=STLTXCont(pps=pps),
            flow_stats=STLFlowLatencyStats(pg_id=2),
        ))

        # --- Queue 3 traffic (PCP 3) - open during window 1 [500-1000 us] ---
        pkt_q3 = (
            Ether(dst="02:00:00:00:00:03")
            / Dot1Q(vlan=vlan_id, prio=3)
            / IP(src="10.0.0.2", dst="10.0.1.1")
            / UDP(sport=5003, dport=5003)
            / (b"\x00" * 256)
        )

        streams.append(STLStream(
            name="q3",
            packet=STLPktBuilder(pkt=pkt_q3),
            mode=STLTXCont(pps=pps),
            flow_stats=STLFlowLatencyStats(pg_id=3),
        ))

        # --- Queue 7 background traffic (PCP 7) - always open (baseline) ---
        pkt_q7 = (
            Ether(dst="02:00:00:00:00:03")
            / Dot1Q(vlan=vlan_id, prio=7)
            / IP(src="10.0.0.2", dst="10.0.1.1")
            / UDP(sport=5007, dport=5007)
            / (b"\x00" * 256)
        )

        streams.append(STLStream(
            name="q7",
            packet=STLPktBuilder(pkt=pkt_q7),
            mode=STLTXCont(pps=bg_pps),
            flow_stats=STLFlowLatencyStats(pg_id=7),
        ))

        return streams


def register():
    return STLTsnTasProfile()
