from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)

def test_queue_until_open(switch, ixn, vports, protocols, add_traffic):
    """
    Verify that frames are queued until gate is open.
    """

    add_traffic(
            name="Talker 1 PCP 2",
            src_proto=protocols[0],
            dst_proto=protocols[2],
            pcp=2,
            start_delay_us=0,
    )
    add_traffic(
            name="Talker 1 PCP 3",
            src_proto=protocols[0],
            dst_proto=protocols[2],
            pcp=3,
            start_delay_us=0,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
