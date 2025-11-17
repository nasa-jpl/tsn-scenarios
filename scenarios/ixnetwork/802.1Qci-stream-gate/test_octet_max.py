from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)


def test_drop_larger_than_octets_max(switch, ixn, vports, protocols, add_traffic):
    """
    Verify frames larger than octets-max are dropped.
    """

    octets_max = 511
    min_size = 64
    max_size = 600

    add_traffic(
        name="Stream 1",
        src_proto=protocols[0],
        dst_proto=protocols[-1],
        start_delay_us=256,
    )
    add_traffic(
        name="Stream 2",
        src_proto=protocols[1],
        dst_proto=protocols[-1],
        start_delay_us=506,
        frame_size = (min_size, max_size),
    )

    # NOTE: Assumes frame size is uniform random range [min_size, max_size]
    expected_loss = (max_size - octets_max) / (max_size - min_size) * 1e2

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_approx_eventually(index=0, stat="Loss %", value=0, abs=1)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_approx_eventually(index=1, stat="Loss %", value=expected_loss, abs=1)
