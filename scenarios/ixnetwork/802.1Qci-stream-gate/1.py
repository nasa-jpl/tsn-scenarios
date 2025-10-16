#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests[socks]>=2.32.4",
#   "ixnetwork-restpy >= 1.7.0",
#   "python-dotenv >= 1.1.1"
# ]
# ///
#
"""
stream_id_scenario4_keysight.py:

   Configure Keysight for Stream Identification, Scenario 4 - IP matching
   Usage of ports 5,6,7 are hardcoded.  Port 5 = EP1, 6 = EP2, 7 = EP3

Supports IxNetwork API servers:
   - Windows, Windows Connection Mgr and Linux

Requirements:
   - Minimum IxNetwork 8.50
   - Python 2.7 and 3+

RestPy Doc:
    https://www.openixia.github.io/ixnetwork_restpy/#/

Usage:
   - Create .env file containing the username and password for the keysight
   - chmod +x <script.py>
   - ./<script.py>

"""

import time
import traceback

from ixnetwork_restpy import StatViewAssistant

from sgfunctions import basecfg

# Provide a name for the keysight session
scenarioName = "stream_gate-1-gating"


try:
    [
        debugMode,
        apiServerIp,
        chassisIp,
        ixNetwork,
        ep1_eth2,
        ep2_eth2,
        tx_port,
        rx_port3,
    ] = basecfg(scenarioName, time, traceback)

    # Configure raw Traffic items.  Comments further down explain some of this.
    trafficTypeList = ["raw", "raw"]

    # Using ep1_topology just demonstrates how, if there is a single protocol stack, you can specify the entire topology,
    # and the keysight will know to use the IPv4 stack as the source since we are generating IPv4 (UDP) packets.
    # The last traffic item, we want raw ethernet frames.
    sourceList = [
        ep1_eth2,
        ep2_eth2,
    ]  # The actual sources used are the virtual ports for EP1 and EP2
    frameRate = [1000, 1000]
    frameDelay = [5, 5]

    ixNetwork.info("Create Traffic Items")
    trafficItem = []
    vlan_outer = []
    print("Creating Traffic Item 1 of", len(sourceList), "...", end="")
    for i in range(len(sourceList)):
        print("\rCreating Traffic Item", i + 1, "of", len(sourceList), "...", end="")
        # Create a traffic item.  This scenario, all traffic is uni-directional.
        # Need to specify the type so that the appropriate packet headers are applied.

        # Add the source and destination.  Note that a variety of types are supported here -
        # you can specify a topology, or a stack like ethernet or IPv4.

        # If you specify something that has multiple stacks, then you get the frames split
        # between them which is typically not what we want.

        # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide
        # the specific IPv4 stack you want to use.
        ##trafficItem[i].EndpointSet.add(Sources=sourceList[i], Destinations=destList[i])

        # Note: A Traffic Item could have multiple EndpointSets (Flow groups).  Therefore, ConfigElement is a list.
        ##configElement = trafficItem[i].ConfigElement.find()[0]

        trafficItem.append(
            ixNetwork.Traffic.TrafficItem.add(
                Name="Traffic Item " + str(i),
                TrafficType=trafficTypeList[i],  # ,
            )
        )

        # Note: Including the endpointset in the traffic item arguments should also work, but didn't (maybe a concurrency issue?)
        endpointSet = trafficItem[i].EndpointSet.add(
            Sources=tx_port[i].Protocols.find(), Destinations=rx_port3.Protocols.find()
        )

        # This scenario doesn't use VLANs but adding this here so somebody starting with this,
        # making a scenario that does use VLANs, knows where to look in the API
        configElement = trafficItem[i].ConfigElement.find()[0]

        # Rest_py template # 71 is VLAN protocol which matches traffic item with web UI
        VlanTagTemplate = ixNetwork.Traffic.ProtocolTemplate.find(DisplayName="^VLAN$")

        # Find the Ethernet stack in the traffic item to append the Vlan header to it
        ethernetStack = configElement.Stack.find(DisplayName="Ethernet")

        # Add the Ethernet, VLAN, and VLAN headers to the packet stack
        # Append the Vlan template to the traffic item Ethernet stack
        ethernetStack.Append(Arg2=VlanTagTemplate)
        print("ethernetStack = ", ethernetStack)

        # Find the newly created Vlan stack object in the traffic item
        VlanTagStack = configElement.Stack.find(DisplayName="^VLAN$")[0]

        # Access the Field collection for the VLAN stack
        vlan_fields = VlanTagStack.Field.find()

        # Find the VLAN ID field and set its value
        vlan_id_field = vlan_fields.find(DisplayName="^VLAN Priority$")
        print("vlan_id_field = ", vlan_id_field)
        vlan_id_field.update(
            SingleValue=0  # Set the VLAN priority to a fixed value of 0
        )
        print("vlan_id_field = ", vlan_id_field)
        # print("dir(ethernetStack.Field) = ",dir(ethernetStack.Field)) ## Use this diagnostic to see the available attributes of an object

        # Attach the ethernet stacks to the corresponding MAC addresses for the endpoints
        # This one is for the destination (EP3)
        ethernetStack.Field.find(
            DisplayName="^Destination MAC Address$"
        ).SingleValue = "00:12:01:00:00:01"

        # This is an alternate way to find/set an Ethernet stack field (eg destination MAC for this example)
        # destination_mac = configElement.Stack.find(StackTypeId='ethernet').Field.find(FieldTypeId='ethernet.header.destinationAddress')
        # destination_mac.update(ValueType='valueList', ValueList=['00:12:01:00:00:01'])

        # These are for the sources (EP1, EP2)
        if i == 0:
            ethernetStack.Field.find(
                DisplayName="^Source MAC Address$"
            ).SingleValue = "00:13:01:00:00:01"
        else:
            ethernetStack.Field.find(
                DisplayName="^Source MAC Address$"
            ).SingleValue = "00:15:01:00:00:01"

        # Set the traffic parameters
        configElement.FrameRate.update(Type="framesPerSecond", Rate=frameRate[i])
        configElement.FrameSize.FixedSize = 64
        configElement.TransmissionControl.update(
            StartDelayUnits="microseconds", StartDelay=frameDelay[i]
        )
        # print("dir(configElement.TransmissionControl) = ",dir(configElement.TransmissionControl))

        # This adds Traffic Item to the Statistics Tracking field.
        # Without this, keysight will not track frame drops, latencies, etc.
        trafficItem[i].Tracking.find()[0].TrackBy = [
            "ethernetIiSourceaddress0",
            "trackingenabled0",
        ]

        ##        sys.exit() # Halts the script

        # This generates the frames based on the previous configuration.
        trafficItem[i].Generate()
        print("Generated traffic...")

        ##sys.exit() # Halts the script

    # This is the loop used to run the test cases for this stream gat escenario; two pases are needed
    for seq in range(2):
        # Sync to gptp time base
        # 1. Get the global Traffic object.
        GlbTraffic = ixNetwork.Traffic
        # print("dir(ixNetwork.Traffic) = ",dir(ixNetwork.Traffic))

        # 2. Set the useScheduledStartTransmit attribute to True.
        # The `useScheduledStartTransmit` setting is located under this object.
        GlbTraffic.UseScheduledStartTransmit = True

        # Not clear why the following steps don't work, but not all the traffic starts (Mike's comments).
        # ixNetwork.Traffic.Apply()
        # ixNetwork.StartAllProtocols(Arg1='sync')
        # ixNetwork.Traffic.Start()

        # This does work, and was discovered using firefox inspector, as what the Web UI is doing when the Green Test Start button is pressed.
        # arg2 = True means to forcefully grab the ports
        # Note that this is non-blocking, but any further operation that relies on the traffic will block until the traffic is started

        print("Starting traffic...")
        ixNetwork.Globals.Testworkflow.Start(arg2=True)

        # Wait until traffic is running
        print("Waiting for traffic to start", end="")
        while not ixNetwork.Traffic.IsTrafficRunning:
            print(".", end="")
            ##time.sleep(0.5)
            time.sleep(2.0)
        print()

        # Wait additional time because if we grab traffic stats instantly, the switch won't have had an
        # opportunity to do the flow metering, and it can take a little while for the keysight stats
        # "moving average" to not reflect the startup transient

        # Wait for the flow statistics to come up allowing for up to 60 seconds before timing out
        statsView = StatViewAssistant(ixNetwork, "Flow Statistics", Timeout=60)
        print("Waiting for statistics to settle...")
        for i in range(10):
            statsView = ixNetwork.Statistics.View.find(Caption="Flow Statistics")
            ##print('statsView = ',statsView)
            time.sleep(1.0)
            # Get the column captions (header names)
            # Get all page values (the actual statistics)
            RxRates = statsView.GetColumnValues(Arg2="Rx Frame Rate")
            print("RxRates = ", RxRates)
            time.sleep(1)

        # time.sleep(3)

        statsView = ixNetwork.Statistics.View.find(Caption="Flow Statistics")
        # print(statsView)

        # For this scenario, success/failure is based on the receive frame rate of each traffic
        # item, matching of Tx/Rx frames to 0.1% for passed traffic and also that no frames are
        # received when the stream gates and frames are not aligned.
        RxRates = statsView.GetColumnValues(Arg2="Rx Frame Rate")

        streamName = ["1", "2"]
        streamTrafficMembers = [0], [1]
        streamExpectedRxRate = [1000.0, 1000.0]
        streamRateUnits = ["Fps", "Fps", "Fps", "Fps"]

        # A tolerance needs to be applied as the Tx/Rx values may be off due to a dropped frame
        # depending on when the traffic item is applied.
        # Using a constant tolerance of 0.1%.

        # print("Before stopping, scheduled_traffic_item = ", scheduled_traffic_item)

        longestName = len(max(streamName, key=len))

        for i in range(len(streamName)):
            rate = 0.0
            expectedRxRate = float(streamExpectedRxRate[i])
            tolerance = expectedRxRate * 0.01

            # Pad with spaces so all names are same length to make output look nice
            name = streamName[i].ljust(longestName)
            if len(streamTrafficMembers[i]) == 0:
                emptyStream = True
            else:
                emptyStream = False
                for j in range(len(streamTrafficMembers[i])):
                    rate += float(RxRates[streamTrafficMembers[i][j]])
            # Should get 0 for frame rate for test 1 and at least 99.9% of the frame rate for  test 2
            if seq == 1:
                testResult = (
                    abs(rate - expectedRxRate) <= tolerance
                )  # Should get 99.9% or more of the frames
            else:
                testResult = abs(rate) == 0.0  # Should be blocked
                expectedRxRate = 0.0
            if emptyStream:
                print(
                    "N/A : Stream",
                    name,
                    "- scenario does not match any traffic items to this stream",
                )
            else:
                if testResult:
                    print("PASS: ", end="")
                else:
                    print("FAIL: ", end="")
                print(
                    "Stream",
                    name,
                    "- expected rate:",
                    expectedRxRate,
                    streamRateUnits[i],
                    "actual rate:",
                    rate,
                    streamRateUnits[i],
                )

        # print("Before stopping, scheduled_traffic_item = ", scheduled_traffic_item)

        # Stop the traffic items after the last test case is complete
        ixNetwork.Globals.Testworkflow.Stop()

        time.sleep(3.0)
        TxFrames = statsView.GetColumnValues(Arg2="Tx Frames")
        RxFrames = statsView.GetColumnValues(Arg2="Rx Frames")
        MaxLatency = statsView.GetColumnValues(Arg2="Store-Forward Max Latency (ns)")
        ##print('TxFrames = ',TxFrames,'RxFrames = ',RxFrames)
        print("frameDelay = ", frameDelay)

        for i in range(len(TxFrames)):
            if seq == 1:
                if TxFrames[i] == RxFrames[i]:
                    print(
                        "Stream Row[",
                        i,
                        "]: ",
                        "TxFrames = ",
                        TxFrames[i],
                        ", RxFrames = ",
                        RxFrames[i],
                        "Max Latency = ",
                        MaxLatency[i],
                        "(ns), PASS: ",
                    )
                elif float(RxFrames[i]) > float(TxFrames[i]) * 0.99:
                    print(
                        "Stream Row[",
                        i,
                        "]: ",
                        "TxFrames = ",
                        TxFrames[i],
                        ", RxFrames = ",
                        RxFrames[i],
                        "Max Latency = ",
                        MaxLatency[i],
                        "(ns), PASS: ",
                    )
                else:
                    print(
                        "Stream Row[",
                        i,
                        "]: ",
                        "TxFrames = ",
                        TxFrames[i],
                        ", RxFrames = ",
                        RxFrames[i],
                        "Max Latency = ",
                        MaxLatency[i],
                        "NA, FAIL: ",
                    )
            else:
                if float(RxFrames[i]) > 0.0:
                    print(
                        "Stream Row[",
                        i,
                        "]: ",
                        "TxFrames = ",
                        TxFrames[i],
                        ", RxFrames = ",
                        RxFrames[i],
                        "Max Latency = ",
                        MaxLatency[i],
                        "(ns), FAIL: ",
                    )
                else:
                    print(
                        "Stream Row[",
                        i,
                        "]: ",
                        "TxFrames = ",
                        TxFrames[i],
                        ", RxFrames = ",
                        RxFrames[i],
                        "Max Latency = ",
                        MaxLatency[i],
                        "NA, PASS: ",
                    )

        ## Modify traffic item start times and rerun
        frameDelay = [255, 505]

        ##SW_status = input("Pause here to check traffic delays ")

        print("Change traffic start delay times; Streams")
        for m in range(len(sourceList)):
            print(
                "\rUpdating start time Traffic Item",
                m + 1,
                "of",
                len(sourceList),
                " to frameDelay = ",
                frameDelay[m],
                " ",
                end="",
            )
            configElement = trafficItem[m].ConfigElement.find()[0]
            configElement.TransmissionControl.update(
                StartDelayUnits="microseconds", StartDelay=frameDelay[m]
            )
            # This adds Traffic Item to the Statistics Tracking field.
            # Without this, keysight will not track frame drops, latencies, etc.
            trafficItem[m].Tracking.find()[0].TrackBy = [
                "ethernetIiSourceaddress0",
                "trackingenabled0",
            ]
            # This generates the frames based on the previous configuration.
            trafficItem[m].Generate()
            print("Generated updated traffic...")

        # Pause the script to change the switch configuration as needed
        SW_status = input("If needed, update the TSN switch now ")
        print(f"Switch status, {SW_status}!")

    print("********Done running tests********")

    if not debugMode:
        for vport in ixNetwork.Vport.find():
            vport.ReleasePort()

except Exception as errMsg:
    print("\n%s" % traceback.format_exc(None, errMsg))
