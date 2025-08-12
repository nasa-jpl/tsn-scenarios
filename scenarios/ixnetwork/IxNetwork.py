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

import sys
import os
import time
import traceback
import yaml

from dotenv import load_dotenv

from ixnetwork_restpy import *


class IxNetwork:

    def __init__(self,
                 api_server_ip,
                 chassis_ip,
                 chassis_slot_number,
                 topology_file,
                 endpoint_file,
                 dry_run=False):

        # Provide username and password to login to Keysight
        load_dotenv()

        self._username = os.getenv('IX_USER')
        self._password = os.getenv('IX_PASS')

        # TODO: Figure out a better / external way to provide deployment-specific information
        # about the Keysight and the port mapping so the demo can be run with different
        # TSN switches wired to different ports

        # Our API server and chassis are same device
        self._api_server_ip = api_server_ip
        self._chassis_ip = chassis_ip

        # Some Keysight products have multiple slots within a single chassis, we just have 1 slot
        self._chassis_slot_number = chassis_slot_number

        # Set dry run flag to allow us to run the setup without affecting the ports on the keysight
        self._dry_run = dry_run

    def _create_packet_header(self,
                              trafficItemObj,
                              packetHeaderToAdd=None,
                              appendToStack=None):
        '''This function is used to create packet headers that can then be manipulated by the caller'''

        configElement = trafficItemObj.ConfigElement.find()

        # Do the followings to add packet headers on the new traffic item

        # Get a list of all the available protocol templates to create (packet headers)
        availableProtocolTemplates = []
        for protocolHeader in ix_network.Traffic.ProtocolTemplate.find():
            availableProtocolTemplates.append(protocolHeader.DisplayName)

        packetHeaderProtocolTemplate = ix_network.Traffic.ProtocolTemplate.find(
            DisplayName='^{}'.format(packetHeaderToAdd))
        if len(packetHeaderProtocolTemplate) == 0:
            ix_network.info(
                '{} protocol template not supported, skipping. Supported procotol templates: {}'
                .format(packetHeaderToAdd,
                        '|'.join(availableProtocolTemplates)))
            return None

        # 2> Append the <new packet header> object after the specified packet header stack.
        appendToStackObj = configElement.Stack.find(
            DisplayName='^{}'.format(appendToStack))
        ix_network.info(
            'Adding protocolTemplate: {} on top of stack: {}'.format(
                packetHeaderProtocolTemplate.DisplayName,
                appendToStackObj.DisplayName))
        if self._debug_mode == True:
            ix_network.info(format(packetHeaderProtocolTemplate))
            ix_network.info(format(appendToStackObj))
            appendToStackObj.Append(Arg2=packetHeaderProtocolTemplate)

        # 3> Get the new packet header stack to use it for appending an IPv4 stack after it.
        # Look for the packet header object and stack ID.
        packetHeaderStackObj = configElement.Stack.find(
            DisplayName='^{}'.format(packetHeaderToAdd))

        # 4> In order to modify the fields, get the field object
        packetHeaderFieldObj = packetHeaderStackObj.Field.find()

        return packetHeaderFieldObj

    def setup_session(self,
                      topology_file,
                      traffic_file,
                      log_file,
                      debug_mode=False,
                      force_take_port_ownership=True,
                      verbosity=SessionAssistant.LOGLEVEL_NONE):
        '''Creates a session with ixnetwork_restpy'''
        # Forcefully take port ownership if the portList are owned by other users.
        self._force_take_port_ownership = True

        # How verbose do we want the output
        self._verbosity = SessionAssistant.LOGLEVEL_NONE
        self._debug_mode = debug_mode

        self._logfile = log_file

        session_name = os.path.basename(log_file)
        session_name, _ = os.path.splitext(session_name)
        self._session_name = session_name

        # Load endpoints
        self._endpoints = yaml.load_safe(toplogy_file)

        # LogLevel: none, info, warning, request, request_response, all
        # all can be useful for debugging issues but is very verbose
        print("Starting Session...")
        session = SessionAssistant(IpAddress=self._api_server_ip,
                                   RestPort=None,
                                   UserName=self._username,
                                   Password=self._password,
                                   SessionName=self._session_name,
                                   SessionId=None,
                                   ApiKey=None,
                                   ClearConfig=True,
                                   LogLevel=self._verbosity,
                                   LogFilename=log_file)

        ix_network = session.Ixnetwork

        print("Assigning Ports...", end="")
        ix_network.info('Assign ports')
        portMap = session.PortMapAssistant()
        # Each port consists of the IP address of the chassis, the card #, and the port #
        vport = dict()
        for name, endpoint in self._endpoints.items():
            vport[name] = portMap.Map(IpAddress=self._chassis_ip,
                                      CardId=self._chassis_slot_number,
                                      PortId=endpoint["ix_port"],
                                      Name=name)

        if self._dry_run == False:
            print("Connecting Ports...")
            portMap.Connect(self._force_take_port_ownership)

        # Setup endpoints
        topologies = dict()
        for name, endpoint in self._endpoints.items():

            print(f'Creating {name} topology...', end='')
            # Go through all device groups in this endpoint
            for i, device_group_name in enumerate(endpoint["device_groups"],
                                                  start=1):
                ix_network.info(f'Creating {name} topology device group {i}')
                topologies[name] = ix_network.Topology.add(Name=name,
                                                           Ports=vport[name])
                ix_group = topologies[name].DeviceGroup.add(
                    Name=f'{name}.DG{i}', Multiplier='1')
                current_device_group = endpoint["device_groups"][
                    "device_group_name"]
                for j, protocol_stack in enumerate(current_device_group,
                                                   start=1):
                    if protocol_stack.startswith("eth"):
                        eth_stack = current_device_group[protocol_stack]
                        ix_eth = ix_group.Ethernet.add(
                            Name=f'{name}.DG{i}.Eth{j}')
                        ix_eth.Mac.Single(value='00:11:01:00:00:01')

                        if "vlan" in eth_stack:
                            ix_eth.EnableVlans.Single(True)
                            ix_eth_vlan = ix_eth.Vlan.find(
                            )[0].VlanId.SingleValue(eth_stack["vlan"])

                        # For IPv4, specify an IP address on the same subnet as the Gateway (by setting prefix to 24, and using the same first 3 numbers x.y.z.*)
                        # The Gateway does not need to exist, but keysight will not generate traffic correctly otherwise
                        # Resolve Gateway needs to be deselected so the keysight does not try to actually access the gateway
                        ix_network.info(f'Configuring {name} IP{j}')
                        ipv4 = ix_eth.Ipv4.add(Name=f'{name}.IP{j}')
                        ipv4.Address.Single(value=eth_stack["ip"])
                        ipv4.Prefix.Single(
                            value=str(eth_stack["gateway_prefix"]))

                        # We assume the gateway prefix is a multiple of 8
                        if (eth_stack["gateway_prefix"] % 8
                                is not 0) or (eth_stack["gateway_prefix"] / 8
                                              > 4):
                            raise ValueError(
                                "Gateway prefix must be either 8, 16, 24, or 32"
                            )

                        num_octets = eth_stack["gateway_prefix"] / 8
                        gateway = ".".join(
                            eth_stack["ip"].split(".")[:num_octets])
                        ipv4.GatewayIp.Single(value=gateway)
                        ipv4.ResolveGateway.Single(False)

        # Congigure traffic by reading in the traffic definition from the traffic yaml file
        self._traffic = yaml.load_safe(traffic_file)

    # Configure UDP Traffic items.  Comments further down explain some of this.
    trafficTypeList = [
        'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4',
        'ipv4', 'ethernetVlan'
    ]

    # Using ep1_topology just demonstrates how, if there is a single protocol stack, you can specify the entire topology,
    # and the keysight will know to use the IPv4 stack as the source since we are generating IPv4 (UDP) packets.
    # The last traffic item, we want raw ethernet frames.
    sourceList = [
        ep1_topology, ip1, ip1, ip1, ip2, ip2, ip2, ip2, ip2, ip2, ep1_eth1
    ]
    destList = [ip3, ip3, ip4, ip4, ip3, ip3, ip4, ip4, ip4, ip3, ep3_eth1]
    udpList = [
        True, True, True, True, True, True, True, True, True, True, False
    ]
    destPort = [1000, 1100, 2000, 2200, 3000, 3300, 4000, 4400, 5000, 5000, 0]
    txRate = [
        10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 19000,
        20000
    ]

    ix_network.info('Create Traffic Items')
    trafficItem = []
    print("Creating Traffic Item 1 of", len(sourceList), "...", end="")
    for i in range(len(sourceList)):
        print(f"\rCreating Traffic Item",
              i + 1,
              "of",
              len(sourceList),
              "...",
              end="")
        # Create a traffic item.  This scenario, all traffic is uni-directional.
        # Need to specify the type so that the appropriate packet headers are applied.
        trafficItem.append(
            ix_network.Traffic.TrafficItem.add(Name='Traffic Item ' + str(i),
                                               BiDirectional=False,
                                               TrafficType=trafficTypeList[i]))

        # Add the source and destination.  Note that a variety of types are supported here -
        # you can specify a topology, or a stack like ethernet or IPv4.

        # If you specify something that has multiple stacks, then you get the frames split
        # between them which is typically not what we want.

        # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide
        # the specific IPv4 stack you want to use.
        trafficItem[i].EndpointSet.add(Sources=sourceList[i],
                                       Destinations=destList[i])

        # Note: A Traffic Item could have multiple EndpointSets (Flow groups).  Therefore, ConfigElement is a list.
        configElement = trafficItem[i].ConfigElement.find()[0]

        # If this traffic item is UDP, add the UDP packet header with appropriate destination port.
        # Our scenario doesn't care about the source port.
        if (udpList[i]):
            udpFieldObj = self._create_packet_header(trafficItem[i],
                                                     packetHeaderToAdd='UDP',
                                                     appendToStack='IPv4')
            udpDstField = udpFieldObj.find(DisplayName='UDP-Dest-Port')
            udpDstField.Auto = False
            udpDstField.SingleValue = destPort[i]

        # Configure for a particular bit rate.  By fixing frame size at 128 bytes, Keysight will determine
        # the correct frame rate to use to achieve the specified bit rate.
        configElement.FrameRate.update(Type='bitsPerSecond',
                                       BitRateUnitsType='kbitsPerSec',
                                       Rate=txRate[i])
        configElement.FrameSize.FixedSize = 128

        # This adds Traffic Item to the Statistics Tracking field.
        # Without this, keysight will not track frame drops, latencies, etc.
        trafficItem[i].Tracking.find()[0].TrackBy = ['trackingenabled0']

        # This generates the frames based on the previous configuration.
        trafficItem[i].Generate()
        print()

    # Not clear why the following steps don't work, but not all the traffic starts.
    # ix_network.Traffic.Apply()
    # ix_network.StartAllProtocols(Arg1='sync')
    # ix_network.Traffic.Start()

    # This does work, and was discovered using firefox inspector, as what the Web UI is doing when the Green Test Start button is pressed.
    # arg2 = True means to forcefully grab the ports
    # Note that this is non-blocking, but any further operation that relies on the traffic will block until the traffic is started

    print("Starting traffic...")
    ix_network.Globals.Testworkflow.Start(arg2=True)

    # Wait until traffic is running
    print("Waiting for traffic to start", end="")
    while (not ix_network.Traffic.IsTrafficRunning):
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
        statsView = ix_network.Statistics.View.find(Caption='Flow Statistics')
        RxRates = statsView.GetColumnValues(Arg2='Rx Rate (Kbps)')
        print(RxRates)
        time.sleep(1)

    # time.sleep(3)

    statsView = ix_network.Statistics.View.find(Caption='Flow Statistics')
    # print(statsView)

    # For this scenario, success/failure is based on the receive bit rate of each traffic
    # item to see that the proper flow meters are applied by the switch.
    RxRates = statsView.GetColumnValues(Arg2='Rx Rate (Kbps)')
    # print("RxRates: ", RxRates)

    streamName = ["1", "2", "3", "4", "5", "6", "N/A (unmetered)"]
    streamTrafficMembers = [[5], [0, 1, 2, 3], [], [6, 7], [4], [8, 9], [10]]
    streamExpectedRxRate = [
        1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 0.0, 20000.0
    ]
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
        if (len(streamTrafficMembers[i]) == 0):
            emptyStream = True
        else:
            emptyStream = False
            for j in range(len(streamTrafficMembers[i])):
                rate += float(RxRates[streamTrafficMembers[i][j]])
                testResult = abs(rate - expectedRxRate) <= tolerance
        if (emptyStream):
            print(
                "N/A : Stream", name,
                "- scenario does not match any traffic items to this stream")
        else:
            if (testResult):
                print("PASS: ", end="")
            else:
                print("FAIL: ", end="")
                print("Stream", name, "- expected rate:", expectedRxRate,
                      streamRateUnits[i], "actual rate:", rate,
                      streamRateUnits[i])

    ix_network.Globals.Testworkflow.Stop()

    if debugMode == False:
        for vport in ix_network.Vport.find():
            vport.ReleasePort()

        # For linux and connection_manager only
        if session.TestPlatform.Platform != 'windows':
            session.Session.remove()
