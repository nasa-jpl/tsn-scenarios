#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv",
#     "ixnetwork_restpy",
# ]
#
# [tool.uv.sources]
# ixn = { path = "../../../tools/ixn", editable = true }
# ///

import os

from dotenv import load_dotenv
from ixnetwork_restpy import SessionAssistant, BatchAdd, TestPlatform, StatViewAssistant

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


def create_frer_topology(ixn, chassis_address, ports):
    with BatchAdd(ixn):
        for i, port in enumerate(ports):
            vport = i + 1
            vp = ixn.Vport.add(Name=vport, Location=f"{chassis_address};1;{port}")
            t = ixn.Topology.add(Vports=vp[-1])
            dg = t.DeviceGroup.add(Multiplier=1)

def create_session(chassis_address, session_name, reuse: bool):
    return SessionAssistant(
        IpAddress=chassis_address,
        UserName=os.getenv("IXN_USER"),
        Password=os.getenv("IXN_PASS"),
        LogLevel=SessionAssistant.LOGLEVEL_INFO,
        ClearConfig=not reuse,
        SessionName=session_name,
    )

def main():
    load_dotenv()

    chassis_address = "hpscnovus"
    verbosity = "info"
    log = None

    ports = [5, 6, 7]
    macs = create_macs()
    session_name = "802.1CB-frer-1"

    session = create_session(chassis_address, session_name, reuse=False)
    ixn = session.Ixnetwork

    create_frer_topology(ixn, chassis_address, ports)

    add_traffic_items(ixn, macs)
    add_egress_only_tracking(ixn)

    ixn.Traffic.Stop()
    stats = session.StatViewAssistant("Port Statistics")

    stream = ixn.Traffic.TrafficItem.find().HighLevelStream.find(Name="^Replicated$")
    stream.StartStatelessTrafficBlocking()
    stats.AddRowFilter(ColumnName="Port Name", Comparator=StatViewAssistant.EQUAL, FilterValue=1)
    stats.CheckCondition(ColumnName="Frames Tx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT)
    stats.CheckCondition(ColumnName="Bytes Tx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT * FRAME_SIZE)
    stats.ClearRowFilters()
    stats.AddRowFilter(ColumnName="Port Name", Comparator=StatViewAssistant.REGEX, FilterValue="2|3")
    stats.CheckCondition(ColumnName="Valid Frames Rx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT)
    stats.CheckCondition(ColumnName="Bytes Rx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT * REPLICATED_FRAME_SIZE)
    stats.ClearRowFilters()
    stream.StopStatelessTrafficBlocking()

    stream = ixn.Traffic.TrafficItem.find().HighLevelStream.find(Name="^Not replicated$")
    stream.StartStatelessTrafficBlocking()
    stats.AddRowFilter(ColumnName="Port Name", Comparator=StatViewAssistant.EQUAL, FilterValue=1)
    stats.CheckCondition(ColumnName="Frames Tx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT)
    stats.CheckCondition(ColumnName="Bytes Tx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT * FRAME_SIZE)
    stats.ClearRowFilters()
    stats.AddRowFilter(ColumnName="Port Name", Comparator=StatViewAssistant.EQUAL, FilterValue=2)
    stats.CheckCondition(ColumnName="Valid Frames Rx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT)
    stats.CheckCondition(ColumnName="Bytes Rx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=FRAME_COUNT * NON_REPLICATED_FRAME_SIZE)
    stats.ClearRowFilters()
    stats.AddRowFilter(ColumnName="Port Name", Comparator=StatViewAssistant.EQUAL, FilterValue=3)
    stats.CheckCondition(ColumnName="Valid Frames Rx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=0)
    stats.CheckCondition(ColumnName="Bytes Rx.", Comparator=StatViewAssistant.EQUAL, ConditionValue=0)
    stats.ClearRowFilters()
    stream.StopStatelessTrafficBlocking()


main()
