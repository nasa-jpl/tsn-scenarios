from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)


def test_drop(switch, ixn, vports, protocols, add_traffic):
    """
    Verify that frames that arrive outside of allowed time slot are dropped.
    """

    add_traffic(
        name="Stream 1",
        src_proto=protocols[0],
        dst_proto=protocols[-1],
        start_delay_us=0,
    )
    add_traffic(
        name="Stream 2",
        src_proto=protocols[1],
        dst_proto=protocols[-1],
        start_delay_us=0,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=0)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=0)


def test_forward(switch, ixn, vports, protocols, add_traffic):
    """
    Verify that frames that arrive inside of allowed time slots are forwarded.
    """

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
