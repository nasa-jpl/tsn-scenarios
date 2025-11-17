from ixnetwork_restpy_helpers import (
    RunTraffic,
    AssertStats,
)


def test_octets_exceeded_status_set(switch, ixn, vports, protocols, add_traffic):
    """
    Verify gateclosedduetooctetsexceeded status is set by frame larger than
    octets max.
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
        frame_size=(64, 600),
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Loss %", value=0)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        # NOTE: Non-deterministic due random frame size.  100% loss starts as soon as
        # frame greater than octet max.
        # flows.assert_approx_eventually(index=1, stat="Loss %", value=expected_loss, abs=1)

    gate_status = switch.get_psfp_gate_status()
    assert gate_status[0]["GateClosedDueToOctetsExceeded"] == 0
    assert gate_status[1]["GateClosedDueToOctetsExceeded"] == 1


def test_drop_due_to_octets_exceeded_status(
    switch, ixn, vports, protocols, add_traffic
):
    """
    Verify small frames are dropped due to gateclosedduetooctetsexceeded status set.
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
        frame_size=64,
    )

    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Loss %", value=0)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Loss %", value=100)

    gate_status = switch.get_psfp_gate_status()
    assert gate_status[0]["GateClosedDueToOctetsExceeded"] == 0
    assert gate_status[1]["GateClosedDueToOctetsExceeded"] == 1

    switch.clear_psfp_gate_closed_due_to_octets_exceeded(stream_id=2)
    gate_status = switch.get_psfp_gate_status()
    assert gate_status[0]["GateClosedDueToOctetsExceeded"] == 0
    assert gate_status[1]["GateClosedDueToOctetsExceeded"] == 0

    # Verify no drops when cleared
    with RunTraffic(ixn):
        flows = AssertStats(ixn, "Flow Statistics")
        flows.assert_equal_eventually(index=0, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=0, stat="Loss %", value=0)
        flows.assert_equal_eventually(index=1, stat="Tx Frame Rate", value=1000)
        flows.assert_equal_eventually(index=1, stat="Loss %", value=0)
