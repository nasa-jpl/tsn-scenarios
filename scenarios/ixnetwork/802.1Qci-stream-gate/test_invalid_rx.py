from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)


def test_forward(switch, ixn, vports, protocols, add_traffic):
    """
    Verify that traffic that conforms to schedule is forwarded.
    """

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
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=1000)


def test_drop_due_to_violation(switch, ixn, vports, protocols, add_traffic):
    """
    Verify nonconformat traffic is dropped and that GateClosedDueToInvalidRx is
    set in the switch.
    """

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
        start_delay_us=5,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=0)

    gate_status = switch.get_psfp_gate_status()
    assert gate_status[0]["GateClosedDueToInvalidRx"] == 0
    assert gate_status[1]["GateClosedDueToInvalidRx"] == 1


def test_drop_due_to_invalid_rx_set(switch, ixn, vports, protocols, add_traffic):
    """
    Verify that traffic continues to be dropped even when conformant due to
    GateClosedDueToInvalidRx status in the switch.

    NOTE: Depends on previous test case running and passing.
    """

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
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=0)

    gate_status = switch.get_psfp_gate_status()
    assert gate_status[0]["GateClosedDueToInvalidRx"] == 0
    assert gate_status[1]["GateClosedDueToInvalidRx"] == 1

    switch.clear_psfp_gate_closed_due_to_invalid_rx(stream_id=2)
    gate_status = switch.get_psfp_gate_status()
    assert gate_status[0]["GateClosedDueToInvalidRx"] == 0
    assert gate_status[1]["GateClosedDueToInvalidRx"] == 0


def test_forward_due_to_rx_invalid_clear(switch, ixn, vports, protocols, add_traffic):
    """
    Verify that conformant traffic now forwards after GateClosedDueToInvalidRx
    is cleared.
    """

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
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Rx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Rx Frame Rate", value=1000)
