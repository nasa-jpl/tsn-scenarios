from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)


def test_queue_until_open(switch, ixn, vports, protocols, add_traffic):
    """
    TAS schedule: [500us PCP 2], [500us PCP 3]
    Send two frames at start of cycle: one with PCP 2, one with PCP 3.
    Verify PCP 2 frame is forwarded immediately.
    Verify PCP 3 frame is queued for ~500us.
    """

    add_traffic(
        name="Talker 1 PCP 2",
        src_idx=0,
        dst_idx=2,
        pcp=2,
        start_delay_us=0,
    )
    add_traffic(
        name="Talker 2 PCP 3",
        src_idx=1,
        dst_idx=2,
        pcp=3,
        start_delay_us=0,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=1000)
        flows.assert_approx_eventually(index=0, stat="Store-Forward Avg Latency (ns)", value=2000, abs=200)
        flows.assert_approx_eventually(index=1, stat="Store-Forward Avg Latency (ns)", value=500000, abs=2000)
