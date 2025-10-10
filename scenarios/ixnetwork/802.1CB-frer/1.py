#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "ixn",
#     "python-dotenv",
# ]
#
# [tool.uv.sources]
# ixn = { path = "../../../tools/ixn", editable = true }
# ///

from dotenv import load_dotenv

from ixn.IxNetwork import IxNetwork

RTAG_ETHER_TYPE = "f1c1"
NOVLAN_ETHER_TYPE_BYTE_OFFSET = 12
VLAN_ETHER_TYPE_BYTE_OFFSET = 16


def create_macs():
    return {
            "nonfrer_talker": "02:00:00:00:00:01",
            "frer_listener": "02:00:00:00:00:02",
            "nonfrer_listener": "02:00:00:00:00:03",
            }


def create_topology(ports: list[int], macs: list[str]):
    assert len(ports) == 3

    endpoints = {
        "endpoints": {},
    }

    for index, (port, mac) in enumerate(zip(ports, macs)):
        name = f"ep{index}"
        ep = {
            "port_num": port,
            "device_groups": {
                "eth1": {
                    "mac": mac,
                },
            },
        }
        endpoints["endpoints"][name] = ep

    return endpoints


def create_traffic_items():
    traffic_items = {
        "traffic_items": {},
    }

    return traffic_items


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
    # FIXME: remove when dev done
    print(ixn.Traffic.TrafficItem.find())
    ixn.Traffic.TrafficItem.find().remove()
    print(ixn.Traffic.TrafficItem.find())

    traffic_item = ixn.Traffic.TrafficItem.add(
        Name="Non-FRER Talker", TrafficType="raw", TrafficItemType="quick"
    )
    vport = ixn.Vport.find()[:1]
    traffic_item.EndpointSet.add(Sources=vport.Protocols.find())
    stream = traffic_item.HighLevelStream.find()
    stream.DuplicateQuickFlowGroups(1)

    streams = traffic_item.HighLevelStream.find()
    set_stream(streams[0], "Replicated", src_addr=macs["nonfrer_talker"], dst_addr=macs["frer_listener"])
    set_stream(streams[1], "Not replicated", src_addr=macs["nonfrer_talker"], dst_addr=macs["nonfrer_listener"])

    ixn.Traffic.Apply()


def set_stream(stream, name, src_addr, dst_addr):
    stream.Name = name
    stream.TransmissionControl.update(
        Type="fixedFrameCount",
        FrameCount=10,
    )
    set_ethernet_stack(stream, src_addr, dst_addr)


def add_egress_only_tracking(ixn):
    ixn.Traffic.EnableEgressOnlyTracking = True

    # FIXME: remove when dev done
    ixn.Traffic.EgressOnlyTracking.find().remove()

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

    print(ixn.Traffic.EgressOnlyTracking.find())


def main():
    load_dotenv()

    chassis_address = "hpscnovus"
    verbosity = "info"
    log = None

    ports = [5, 6, 7]
    macs = create_macs()
    endpoints = create_topology(ports, macs.values())
    traffic_items = create_traffic_items()
    session_name = "802.1CB-frer-1"

    jixn = IxNetwork(chassis_address, chassis_address, 1, session_name, verbosity, log)
    jixn.create_session(endpoints, traffic_items, dry_run=False, force_port_ownership=True)
    # jixn._ix_session = jixn._get_session_by_name()
    ixn = jixn._ix_session.Ixnetwork

    add_traffic_items(ixn, macs)
    add_egress_only_tracking(ixn)


main()
