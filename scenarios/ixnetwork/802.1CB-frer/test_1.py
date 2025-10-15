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
CTAG_SIZE = 4
RTAG_SIZE = 6

FRAME_COUNT = 10
FRAME_SIZE = 64
FRAME_SIZE_REPLICATED = FRAME_SIZE + CTAG_SIZE + RTAG_SIZE
FRAME_SIZE_NONREPLICATED = FRAME_SIZE

ADDR_NONFRER_TALKER = "02:00:00:00:00:01"
ADDR_FRER_LISTENER = "02:00:00:00:00:02"
ADDR_NONFRER_LISTENER = "02:00:00:00:00:03"


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
                except Exception:
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
def add_traffic(ixn):
    def _add_traffic(name, src_addr, dst_addr):
        traffic_item = ixn.Traffic.TrafficItem.add(
            Name=name,
            TrafficType="raw",
            TrafficItemType="quick",
        )
        vport = ixn.Vport.find()[0]
        traffic_item.EndpointSet.add(Sources=vport.Protocols.find())

        stream = traffic_item.HighLevelStream.find()
        stream.FrameSize.update(
            Type="fixed",
            FixedSize=FRAME_SIZE,
        )
        stream.TransmissionControl.update(
            Type="fixedFrameCount",
            FrameCount=FRAME_COUNT,
        )

        ethernet_stack = stream.Stack.find(StackTypeId="^ethernet$")
        ethernet_stack.Field.find(Name="sourceAddress").SingleValue = src_addr
        ethernet_stack.Field.find(Name="destinationAddress").SingleValue = dst_addr

        ixn.Traffic.Apply()

        return traffic_item

    yield _add_traffic

    ixn.Traffic.TrafficItem.find().remove()
    ixn.ClearStats()


def test_replication(ixn, topology, add_traffic):
    traffic = add_traffic(
        name="Replicated", src_addr=ADDR_NONFRER_TALKER, dst_addr=ADDR_FRER_LISTENER
    )

    traffic.StartStatelessTrafficBlocking()
    time.sleep(5)
    traffic.StopStatelessTrafficBlocking()

    ports = StatsView(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_REPLICATED
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_REPLICATED


def test_nonreplication(ixn, topology, add_traffic):
    traffic = add_traffic(
        name="Not replicated",
        src_addr=ADDR_NONFRER_TALKER,
        dst_addr=ADDR_NONFRER_LISTENER,
    )

    traffic.StartStatelessTrafficBlocking()
    time.sleep(5)
    traffic.StopStatelessTrafficBlocking()

    ports = StatsView(ixn, "Port Statistics")
    assert ports[0]["Frames Tx."] == FRAME_COUNT
    assert ports[0]["Bytes Tx."] == FRAME_COUNT * FRAME_SIZE
    assert ports[1]["Valid Frames Rx."] == FRAME_COUNT
    assert ports[1]["Bytes Rx."] == FRAME_COUNT * FRAME_SIZE_NONREPLICATED
    assert ports[2]["Valid Frames Rx."] == 0
    assert ports[2]["Bytes Rx."] == 0
