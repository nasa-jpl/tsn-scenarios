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

import sys, os, time, traceback

from dotenv import load_dotenv

from ixnetwork_restpy import *

# Provide username and password to login to Keysight
load_dotenv()

if proxy := os.getenv("IXN_PROXY"):
    os.environ["ALL_PROXY"] = proxy
username = os.getenv("IXN_USER")
password = os.getenv("IXN_PASS")

# TODO: Figure out a better / external way to provide deployment-specific information about the Keysight and the port mapping so the demo can be run with different TSN switches wired to different ports

# Provide a name for the keysight session
scenarioName = "stream_id-4-ip_matching"

# Our API server and chassis are same device
apiServerIp = os.getenv("IXN_ADDRESS")
chassisIp = os.getenv("IXN_ADDRESS")

# Some Keysight products have multiple slots within a single chassis, we just have 1 slot
chassisSlotNumber = 1

# Each port consists of the IP address of the chassis, the card #, and the port #
ports = [int(port) for port in os.getenv("IXN_PORTS").split(",")]
portList = [[chassisIp, chassisSlotNumber, port] for port in ports]


outLogFile: str = scenarioName + "_" + time.strftime("%Y%m%d-%H%M%S") + ".log"

# For linux and connection_manager only. Set to True to leave the session alive for debugging.
debugMode = True

# Forcefully take port ownership if the portList are owned by other users.
forceTakePortOwnership = True

# How verbose do we want the output
verbosity = SessionAssistant.LOGLEVEL_NONE

try:

    def createPacketHeader(trafficItemObj, packetHeaderToAdd=None, appendToStack=None):
        configElement = trafficItemObj.ConfigElement.find()

        # Do the followings to add packet headers on the new traffic item

        # Get a list of all the available protocol templates to create (packet headers)
        availableProtocolTemplates = []
        for protocolHeader in ixNetwork.Traffic.ProtocolTemplate.find():
            availableProtocolTemplates.append(protocolHeader.DisplayName)

        packetHeaderProtocolTemplate = ixNetwork.Traffic.ProtocolTemplate.find(
            DisplayName="^{}".format(packetHeaderToAdd)
        )
        if len(packetHeaderProtocolTemplate) == 0:
            ixNetwork.info(
                "{} protocol template not supported, skipping. Supported procotol templates: {}".format(
                    packetHeaderToAdd, "|".join(availableProtocolTemplates)
                )
            )
            return None

        # 2> Append the <new packet header> object after the specified packet header stack.
        appendToStackObj = configElement.Stack.find(
            DisplayName="^{}".format(appendToStack)
        )
        ixNetwork.info(
            "Adding protocolTemplate: {} on top of stack: {}".format(
                packetHeaderProtocolTemplate.DisplayName, appendToStackObj.DisplayName
            )
        )
        if debugMode:
            ixNetwork.info(format(packetHeaderProtocolTemplate))
            ixNetwork.info(format(appendToStackObj))
        appendToStackObj.Append(Arg2=packetHeaderProtocolTemplate)

        # 3> Get the new packet header stack to use it for appending an IPv4 stack after it.
        # Look for the packet header object and stack ID.
        packetHeaderStackObj = configElement.Stack.find(
            DisplayName="^{}".format(packetHeaderToAdd)
        )

        # 4> In order to modify the fields, get the field object
        packetHeaderFieldObj = packetHeaderStackObj.Field.find()

        return packetHeaderFieldObj

    # LogLevel: none, info, warning, request, request_response, all
    # all can be useful for debugging issues but is very verbose
    print("Starting Session...")
    session = SessionAssistant(
        IpAddress=apiServerIp,
        RestPort=None,
        UserName=username,
        Password=password,
        SessionName=scenarioName,
        SessionId=None,
        ApiKey=None,
        ClearConfig=True,
        LogLevel=verbosity,
        LogFilename=outLogFile,
    )

    ixNetwork = session.Ixnetwork

    print("Assigning Ports...", end="")
    ixNetwork.info("Assign ports")
    portMap = session.PortMapAssistant()
    vport = dict()
    for index, port in enumerate(portList):
        portName = "Port_EP{}".format(index + 1)
        vport[portName] = portMap.Map(
            IpAddress=port[0], CardId=port[1], PortId=port[2], Name=portName
        )

    print("Connecting Ports...")
    portMap.Connect(forceTakePortOwnership)

    # TODO: Figure out a better way to organize (end point class???) and consider if there is a better naming convention

    # Also, it appears that if we want specifically "talkers" on the left and "listeners" on the right in the graphical topology,
    # we have to create the end points in order EP1, EP3, EP2.  Have not found a way to specify which side in the layout to put it,
    # it just seems to alternate left-right-left-right.

    # Setup EP1
    # To send or receive data on a port on Keysight, you need a 'topology' which contains 1 or more 'device groups'
    # which contains 1 or more 'protocol stacks'.  The protocol stacks for TSN scenarios always start with Ethernet.
    # If using raw ethernet (with or without VLANs), that is all that is needed.  If using IPv4, that is added on top of the Ethernet.
    print("Creating Topology 1 of 3...", end="")
    ixNetwork.info("Creating Topology Group 1")
    ep1_topology = ixNetwork.Topology.add(Name="EP1", Ports=vport["Port_EP1"])
    ep1_dg1 = ep1_topology.DeviceGroup.add(Name="EP1.DG1", Multiplier="1")
    ep1_eth1 = ep1_dg1.Ethernet.add(Name="EP1.DG1.Eth1")

    # Note that there are are certain uses for some of the upper bits of MAC address.  Recommend always using 00 for the most significant 8 bits.
    ep1_eth1.Mac.Single(value="00:11:01:00:00:01")

    # This scenario doesn't use VLANs but leaving this here so somebody starting with this,
    # making a scenario that does use VLANs, knows where to look in the API

    # ep1_eth1.EnableVlans.Single(True)
    # ep1_eth1_vlan = ep1_eth1.Vlan.find()[0].VlanId.SingleValue(2)

    # For IPv4, specify an IP address on the same subnet as the Gateway (by setting prefix to 24, and using the same first 3 numbers x.y.z.*)
    # The Gateway does not need to exist, but keysight will not generate traffic correctly otherwise
    # Resolve Gateway needs to be deselected so the keysight does not try to actually access the gateway
    ixNetwork.info("Configuring EP1 IP1")
    ip1 = ep1_eth1.Ipv4.add(Name="EP1.IP1")
    ip1.Address.Single(value="100.1.0.1")
    ip1.Prefix.Single(value="24")
    ip1.GatewayIp.Single(value="100.1.0.10")
    ip1.ResolveGateway.Single(False)

    # Setup EP3
    # For this scenario there are 2 separate stacks with separate IP addresses
    print(f"\rCreating Topology 2 of 3...", end="")

    ixNetwork.info("Creating Topology Group 3")
    ep3_topology = ixNetwork.Topology.add(Name="EP3", Ports=vport["Port_EP3"])
    ep3_dg1 = ep3_topology.DeviceGroup.add(Name="EP3.DG1", Multiplier="1")
    ep3_eth1 = ep3_dg1.Ethernet.add(Name="EP3.DG1.Eth1")
    ep3_eth1.Mac.Single(value="00:11:01:00:00:03")

    ixNetwork.info("Configuring EP3 IP3")
    ip3 = ep3_eth1.Ipv4.add(Name="EP3.IP3")
    ip3.Address.Single(value="100.1.0.3")
    ip3.Prefix.Single(value="24")
    ip3.GatewayIp.Single(value="100.1.0.10")
    ip3.ResolveGateway.Single(False)

    ep3_eth2 = ep3_dg1.Ethernet.add(Name="EP3.DG.Eth2")
    ep3_eth2.Mac.Single(value="00:11:01:00:00:04")

    ixNetwork.info("Configuring EP3 IP4")
    ip4 = ep3_eth2.Ipv4.add(Name="EP3.IP4")
    ip4.Address.Single(value="100.1.0.4")
    ip4.Prefix.Single(value="24")
    ip4.GatewayIp.Single(value="100.1.0.10")
    ip4.ResolveGateway.Single(False)

    # Setup EP2
    print(f"\rCreating Topology 3 of 3...")

    ixNetwork.info("Creating Topology Group 2")
    ep2_topology = ixNetwork.Topology.add(Name="EP2", Ports=vport["Port_EP2"])
    ep2_dg1 = ep2_topology.DeviceGroup.add(Name="EP2.DG1", Multiplier="1")
    ep2_eth1 = ep2_dg1.Ethernet.add(Name="EP2.DG1.Eth1")
    ep2_eth1.Mac.Single(value="00:11:01:00:00:02")

    ixNetwork.info("Configuring EP2 IP2")
    ip2 = ep2_eth1.Ipv4.add(Name="EP2.IP2")
    ip2.Address.Single(value="100.1.0.2")
    ip2.Prefix.Single(value="24")
    ip2.GatewayIp.Single(value="100.1.0.10")
    ip2.ResolveGateway.Single(False)

    # Configure UDP Traffic items.  Comments further down explain some of this.
    trafficTypeList = [
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ipv4",
        "ethernetVlan",
    ]

    # Using ep1_topology just demonstrates how, if there is a single protocol stack, you can specify the entire topology,
    # and the keysight will know to use the IPv4 stack as the source since we are generating IPv4 (UDP) packets.
    # The last traffic item, we want raw ethernet frames.
    sourceList = [ep1_topology, ip1, ip1, ip1, ip2, ip2, ip2, ip2, ip2, ip2, ep1_eth1]
    destList = [ip3, ip3, ip4, ip4, ip3, ip3, ip4, ip4, ip4, ip3, ep3_eth1]
    udpList = [True, True, True, True, True, True, True, True, True, True, False]
    destPort = [1000, 1100, 2000, 2200, 3000, 3300, 4000, 4400, 5000, 5000, 0]
    txRate = [
        10000,
        11000,
        12000,
        13000,
        14000,
        15000,
        16000,
        17000,
        18000,
        19000,
        20000,
    ]

    ixNetwork.info("Create Traffic Items")
    trafficItem = []
    print("Creating Traffic Item 1 of", len(sourceList), "...", end="")
    for i in range(len(sourceList)):
        print(f"\rCreating Traffic Item", i + 1, "of", len(sourceList), "...", end="")
        # Create a traffic item.  This scenario, all traffic is uni-directional.
        # Need to specify the type so that the appropriate packet headers are applied.
        trafficItem.append(
            ixNetwork.Traffic.TrafficItem.add(
                Name="Traffic Item " + str(i),
                BiDirectional=False,
                TrafficType=trafficTypeList[i],
            )
        )

        # Add the source and destination.  Note that a variety of types are supported here -
        # you can specify a topology, or a stack like ethernet or IPv4.

        # If you specify something that has multiple stacks, then you get the frames split
        # between them which is typically not what we want.

        # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide
        # the specific IPv4 stack you want to use.
        trafficItem[i].EndpointSet.add(Sources=sourceList[i], Destinations=destList[i])

        # Note: A Traffic Item could have multiple EndpointSets (Flow groups).  Therefore, ConfigElement is a list.
        configElement = trafficItem[i].ConfigElement.find()[0]

        # If this traffic item is UDP, add the UDP packet header with appropriate destination port.
        # Our scenario doesn't care about the source port.
        if udpList[i]:
            udpFieldObj = createPacketHeader(
                trafficItem[i], packetHeaderToAdd="UDP", appendToStack="IPv4"
            )
            udpDstField = udpFieldObj.find(DisplayName="UDP-Dest-Port")
            udpDstField.Auto = False
            udpDstField.SingleValue = destPort[i]

        # Configure for a particular bit rate.  By fixing frame size at 128 bytes, Keysight will determine
        # the correct frame rate to use to achieve the specified bit rate.
        configElement.FrameRate.update(
            Type="bitsPerSecond", BitRateUnitsType="kbitsPerSec", Rate=txRate[i]
        )
        configElement.FrameSize.FixedSize = 128

        # This adds Traffic Item to the Statistics Tracking field.
        # Without this, keysight will not track frame drops, latencies, etc.
        trafficItem[i].Tracking.find()[0].TrackBy = ["trackingenabled0"]

        # This generates the frames based on the previous configuration.
        trafficItem[i].Generate()
    print()

    # Not clear why the following steps don't work, but not all the traffic starts.
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
        time.sleep(0.5)
    print()

    # Wait additional time because if we grab traffic stats instantly, the switch won't have had an
    # opportunity to do the flow metering, and it can take a little while for the keysight stats
    # "moving average" to not reflect the startup transient

    # TODO: Using this code snippet, sometimes the rates are settled by 2 seconds, usually 3, sometimes more
    # Leaving this in for debugging purposes.
    # One possibility is to make a scenario-specific check, like wait until some rate is within tolerance of
    # the expected value, but that might just get stuck waiting if the switch or keysight are not configured correctly
    # Another method could be to calculate the rate of change of every stats item of interest and wait until some convergence across the majority of them.

    print("Waiting for statistics to settle...")
    for i in range(10):
        statsView = ixNetwork.Statistics.View.find(Caption="Flow Statistics")
        RxRates = statsView.GetColumnValues(Arg2="Rx Rate (Kbps)")
        print(RxRates)
        time.sleep(1)

    # time.sleep(3)

    statsView = ixNetwork.Statistics.View.find(Caption="Flow Statistics")
    # print(statsView)

    # For this scenario, success/failure is based on the receive bit rate of each traffic
    # item to see that the proper flow meters are applied by the switch.
    RxRates = statsView.GetColumnValues(Arg2="Rx Rate (Kbps)")
    # print("RxRates: ", RxRates)

    streamName = ["1", "2", "3", "4", "5", "6", "N/A (unmetered)"]
    streamTrafficMembers = [[5], [0, 1, 2, 3], [], [6, 7], [4], [8, 9], [10]]
    streamExpectedRxRate = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 0.0, 20000.0]
    streamRateUnits = ["Kbps", "Kbps", "Kbps", "Kbps", "Kbps", "Kbps", "Kbps"]

    # A tolerance needs to be applied as the values won't be exact based on how the flow meter is applied.
    # Currently, there seems to be some source of error we have not figured out, so the tolerance
    # needs to be a bit higher than ideal.  For example, a flow restricted to 5000 Kbps we might see 5020 Kbps.
    # The error seems to be more a constant than a ratio of the traffic, so a flow restricted to 100 Kbps might see 120 Kbps.
    # For now, using a constant tolerance of 1% but that might not work for scenarios using lower flow meter rates.

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
        testResult = abs(rate - expectedRxRate) <= tolerance
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

    ixNetwork.Globals.Testworkflow.Stop()

    if debugMode == False:
        for vport in ixNetwork.Vport.find():
            vport.ReleasePort()

        # For linux and connection_manager only
        if session.TestPlatform.Platform != "windows":
            session.Session.remove()

except Exception as errMsg:
    print("\n%s" % traceback.format_exc(None, errMsg))
    if debugMode == False and "session" in locals():
        if session.TestPlatform.Platform != "windows":
            session.Session.remove()
