#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv",
#     "ixnetwork_restpy",
# ]
# ///

import time

from ixnetwork_restpy import BatchAdd
import pytest

RTAG_ETHER_TYPE = "f1c1"
NOVLAN_ETHER_TYPE_BYTE_OFFSET = 12
VLAN_ETHER_TYPE_BYTE_OFFSET = 16

FRAME_COUNT = 10
FRAME_SIZE = 64
CTAG_SIZE = 4
RTAG_SIZE = 6
REPLICATED_FRAME_SIZE = FRAME_SIZE + CTAG_SIZE + RTAG_SIZE
NON_REPLICATED_FRAME_SIZE = FRAME_SIZE


def create_macs():
    return {
        "nonfrer_talker": "02:00:00:00:00:01",
        "frer_listener": "02:00:00:00:00:02",
        "nonfrer_listener": "02:00:00:00:00:03",
    }


def set_ethernet_stack(stream, src_addr, dst_addr):
    # custom_protocol_template = ixn.Traffic.ProtocolTemplate.find(StackTypeId="^custom$")

    ethernet_stack = stream.Stack.find(StackTypeId="^ethernet$")
    # rtag_rsvd_stack = stream.Stack.read(
    #     ethernet_stack.AppendProtocol(custom_protocol_template)
    # )
    # rtag_seqid_stack = stream.Stack.read(
    #     rtag_rsvd_stack.AppendProtocol(custom_protocol_template)
    # )

    # Set src and dst addresses
    ethernet_stack.Field.find(Name="sourceAddress").SingleValue = src_addr
    ethernet_stack.Field.find(Name="destinationAddress").SingleValue = dst_addr

    # # Add R-Tag
    # ethernet_stack.Field.find(Name="ether_type").update(
    #     Auto=False,
    #     SingleValue=RTAG_ETHER_TYPE,
    # )
    # rtag_rsvd_stack.Field.find(Name="Length").SingleValue = 16
    # rtag_seqid_stack.Field.find(Name="Length").SingleValue = 16
    # rtag_seqid_stack.Field.find(Name="Data").update(
    #     ValueType="increment",
    #     StartValue=1,
    #     StepValue=1,
    #     CountValue=65535,
    # )


# Add quick flow group that generates r-tagged traffic
def add_traffic_items(ixn, macs):
    traffic_item = ixn.Traffic.TrafficItem.add(
        Name="Non-FRER Talker", TrafficType="raw", TrafficItemType="quick"
    )
    vport = ixn.Vport.find()[:1]
    traffic_item.EndpointSet.add(Sources=vport.Protocols.find())
    stream = traffic_item.HighLevelStream.find()
    stream.DuplicateQuickFlowGroups(1)

    streams = traffic_item.HighLevelStream.find()
    set_stream(
        streams[0],
        "Replicated",
        src_addr=macs["nonfrer_talker"],
        dst_addr=macs["frer_listener"],
    )
    set_stream(
        streams[1],
        "Not replicated",
        src_addr=macs["nonfrer_talker"],
        dst_addr=macs["nonfrer_listener"],
    )
    ixn.Traffic.Apply()


def set_stream(stream, name, src_addr, dst_addr):
    stream.Name = name
    stream.FrameSize.update(
        Type="fixed",
        FixedSize=FRAME_SIZE,
    )
    stream.TransmissionControl.update(
        Type="fixedFrameCount",
        FrameCount=FRAME_COUNT,
    )
    set_ethernet_stack(stream, src_addr, dst_addr)


def add_egress_only_tracking(ixn):
    ixn.Traffic.EnableEgressOnlyTracking = True

    vports = ixn.Vport.find()[-2:]

    for vport in vports:
        vport.AddEgressOnlyTracking()

    for eot in ixn.Traffic.EgressOnlyTracking.find():
        egress = [
            # NOTE: This allows bins to be created based on packet contents
            # (e.g., one bin per priority).  Arg1 is a byte offset into the
            # packet and arg2 is a bit mask where a zero value includes the
            # bit and a one value excludes the bit. We aren't insterested
            # in multiple bins but IxNetwork requires at least two so at
            # least one bit needs to be unmasked (zero).  So we unmask the
            # first bit.
            {"arg1": 0, "arg2": "7fffffff"},
            {"arg1": 0, "arg2": "ffffffff"},
            {"arg1": 0, "arg2": "ffffffff"},
        ]
        eot.update(
            Egress=egress,
            SignatureOffset=NOVLAN_ETHER_TYPE_BYTE_OFFSET,
            SignatureValue=RTAG_ETHER_TYPE + "0000",
        )

    ixn.Traffic.Apply()


class StatsView:
    def __init__(self, ixn, view_caption):
        self._view = ixn.Statistics.View.find(Caption=f"^{view_caption}$")
        self._snapshot = self._snapshot()

    def _snapshot(self):
        cols = self._view.Data.ColumnCaptions
        rows = self._view.Data.RowValues.values()
        rows = [row[0] for row in rows]

        return self._list_of_lists_to_list_of_dicts(rows, cols)

    def _list_of_lists_to_list_of_dicts(
        self, list_of_lists: list[list[str]], column_captions: list[str]
    ) -> list[dict[str, str]]:
        list_of_dicts = []
        for row in list_of_lists:
            row_dict = {}
            for i, cell in enumerate(row):
                key = column_captions[i]
                try:
                    row_dict[key] = int(cell)
                except:
                    row_dict[key] = cell
            list_of_dicts.append(row_dict)
        return list_of_dicts

    def __getitem__(self, i):
        return self._snapshot[i]


@pytest.fixture(scope="module")
def topology(config, ixn):
    chassis = config["chassis"]
    ports = config["ports"]

    with BatchAdd(ixn):
        for i, port in enumerate(ports):
            vport = i + 1
            vp = ixn.Vport.add(Name=vport, Location=f"{chassis};1;{port}")
            t = ixn.Topology.add(Vports=vp[-1])
            t.DeviceGroup.add(Multiplier=1)


@pytest.fixture
def traffic(ixn):
    macs = create_macs()
    add_traffic_items(ixn, macs)
    yield
    ixn.Traffic.TrafficItem.find().remove()
    ixn.ClearStats()


def test_replication(ixn, topology, traffic):
    stream = ixn.Traffic.TrafficItem.find().HighLevelStream.find(Name="^Replicated$")
    stream.StartStatelessTrafficBlocking()
    time.sleep(1)
    stream.StopStatelessTrafficBlocking()

    ports = StatsView(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * REPLICATED_FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * REPLICATED_FRAME_SIZE


def test_nonreplication(ixn, topology, traffic):
    stream = ixn.Traffic.TrafficItem.find().HighLevelStream.find(
        Name="^Not replicated$"
    )
    stream.StartStatelessTrafficBlocking()
    time.sleep(1)
    stream.StopStatelessTrafficBlocking()
    ports = StatsView(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * NON_REPLICATED_FRAME_SIZE
    assert ports[2]["Valid Frames Rx."] == 0
    assert ports[2]["Bytes Rx."] == 0
