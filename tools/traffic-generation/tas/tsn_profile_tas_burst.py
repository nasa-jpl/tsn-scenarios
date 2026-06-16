from trex_stl_lib.api import (
    STLProfile,
    STLStream,
    STLTXCont,
    STLTXSingleBurst,
    STLPktBuilder,
    STLFlowLatencyStats,
    STLFlowStats,
    STLScVmRaw,
    STLVmFlowVar,
    STLVmWrFlowVar,
    STLVmFixChecksumHw,
    CTRexVmInsFixHwCs,
)
from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP


# Payload layout: [seq (4 bytes)] [padding]
# Offset from frame start: Ether(14) + VLAN(4) + IP(20) + UDP(8) = 46
PAYLOAD_SEQ_OFFSET = 46


class STLTsnTasBurstProfile(object):
    """TSN burst traffic profile aligned to 802.1Qbv TAS gate windows.

    TAS gate schedule on the switch egress port (1 ms cycle):
      Window 0 [  0 - 500 us]: queues 2, 7 open
      Window 1 [500 - 1000 us]: queues 3, 7 open

    Queue 2 and Queue 3 send alternating 500 us bursts aligned to their
    respective gate windows, with a 500 us pause in between (while the
    other queue's gate is open).  Queue 7 is continuous background.

    The 1 ms burst+pause cycle matches the TAS gate cycle so traffic
    arrives only during the open window for each queue.

    Each packet carries a 4-byte incrementing sequence number at the
    start of the UDP payload (via the field engine) so the dashboard
    can match ingress/egress packets for tap latency measurement.

    kwargs:
      vlan_id    — VLAN ID (default 3)
      burst_pkts — packets per burst for q2/q3 (default 50)
      burst_pps  — rate within each burst (default 100000)
      bg_pps     — queue 7 continuous rate (default 1000)
    """

    def __init__(self):
        pass

    def _make_vm(self):
        """Field engine: write a per-packet random 64-bit ID to payload."""
        return STLScVmRaw([
            STLVmFlowVar(name="pkt_id", min_value=1, max_value=0xFFFFFFFFFFFFFFFF,
                         size=8, op="random"),
            STLVmWrFlowVar(fv_name="pkt_id", pkt_offset=PAYLOAD_SEQ_OFFSET),
            STLVmFixChecksumHw(l3_offset=14 + 4, l4_offset=14 + 4 + 20,
                               l4_type=CTRexVmInsFixHwCs.L4_TYPE_UDP),
        ])

    def get_streams(self, direction=0, **kwargs):
        vlan_id = kwargs.get("vlan_id", 3)
        burst_pkts = kwargs.get("burst_pkts", 100)
        burst_pps = kwargs.get("burst_pps", 50000)
        bg_pps = kwargs.get("bg_pps", 1000)

        vm = self._make_vm()
        streams = []

        # --- Queue 2 (PCP 2): burst during window 0, pause during window 1 ---
        pkt_q2 = (
            Ether(dst="02:00:00:00:00:03")
            / Dot1Q(vlan=vlan_id, prio=2)
            / IP(src="10.0.0.2", dst="10.0.1.1")
            / UDP(sport=5002, dport=5002)
            / (b"\x00" * 64)
        )

        streams.append(STLStream(
            name="q2_burst",
            packet=STLPktBuilder(pkt=pkt_q2, vm=vm),
            mode=STLTXSingleBurst(pps=burst_pps, total_pkts=burst_pkts),
            flow_stats=STLFlowStats(pg_id=2),
            isg=0,
            self_start=True,
            next="q2_pause",
        ))

        streams.append(STLStream(
            name="q2_pause",
            packet=STLPktBuilder(pkt=pkt_q2, vm=vm),
            mode=STLTXSingleBurst(pps=burst_pps, total_pkts=1),
            isg=500,  # 500 us pause (window 1 duration)
            self_start=False,
            next="q2_burst",
        ))

        # --- Queue 3 (PCP 3): burst during window 1, pause during window 0 ---
        pkt_q3 = (
            Ether(dst="02:00:00:00:00:03")
            / Dot1Q(vlan=vlan_id, prio=3)
            / IP(src="10.0.0.2", dst="10.0.1.1")
            / UDP(sport=5003, dport=5003)
            / (b"\x00" * 64)
        )

        streams.append(STLStream(
            name="q3_burst",
            packet=STLPktBuilder(pkt=pkt_q3, vm=vm),
            mode=STLTXSingleBurst(pps=burst_pps, total_pkts=burst_pkts),
            flow_stats=STLFlowStats(pg_id=3),
            isg=500,  # 500 us offset — start at window 1
            self_start=True,
            next="q3_pause",
        ))

        streams.append(STLStream(
            name="q3_pause",
            packet=STLPktBuilder(pkt=pkt_q3, vm=vm),
            mode=STLTXSingleBurst(pps=burst_pps, total_pkts=1),
            isg=500,  # 500 us pause (window 0 duration)
            self_start=False,
            next="q3_burst",
        ))

        # --- Queue 7 (PCP 7): continuous background, always open ---
        pkt_q7 = (
            Ether(dst="02:00:00:00:00:03")
            / Dot1Q(vlan=vlan_id, prio=7)
            / IP(src="10.0.0.2", dst="10.0.1.1")
            / UDP(sport=5007, dport=5007)
            / (b"\x00" * 64)
        )

        streams.append(STLStream(
            name="q7",
            packet=STLPktBuilder(pkt=pkt_q7, vm=self._make_vm()),
            mode=STLTXCont(pps=bg_pps),
            flow_stats=STLFlowLatencyStats(pg_id=7),
        ))

        return streams


def register():
    return STLTsnTasBurstProfile()
