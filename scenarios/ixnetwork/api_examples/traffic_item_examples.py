#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "ixnetwork-restpy >= 1.7.0",
#   "python-dotenv >= 1.1.1"
# ]
# ///
# 
"""
traffic_item_examples.py:

   Demonstrate how to generate a variety of traffic types used in various TSN scenarios
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
scenarioName = 'traffic_item_examples'

# Our API server and chassis are same device
apiServerIp = os.getenv("IXN_ADDRESS")
chassisIp = os.getenv("IXN_ADDRESS")

# Some Keysight products have multiple slots within a single chassis, we just have 1 slot
chassisSlotNumber = 1

# Each port consists of the IP address of the chassis, the card #, and the port #
ports = [int(port) for port in os.getenv("IXN_PORTS").split(",")]
portList = [[chassisIp, chassisSlotNumber, port] for port in ports]


outLogFile : str = scenarioName + '_' + time.strftime("%Y%m%d-%H%M%S") + '.log'

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
                     
        packetHeaderProtocolTemplate = ixNetwork.Traffic.ProtocolTemplate.find(DisplayName='^{}'.format(packetHeaderToAdd))
        if len(packetHeaderProtocolTemplate) == 0:
            ixNetwork.info('{} protocol template not supported, skipping. Supported procotol templates: {}'.format(packetHeaderToAdd,
                '|'.join(availableProtocolTemplates)))
            return None
        
        # 2> Append the <new packet header> object after the specified packet header stack.
        appendToStackObj = configElement.Stack.find(DisplayName='^{}'.format(appendToStack))
        ixNetwork.info('Adding protocolTemplate: {} on top of stack: {}'.format(packetHeaderProtocolTemplate.DisplayName,
                        appendToStackObj.DisplayName))
        if debugMode:                
            ixNetwork.info(format(packetHeaderProtocolTemplate))        
            ixNetwork.info(format(appendToStackObj))
        appendToStackObj.Append(Arg2=packetHeaderProtocolTemplate)

        # 3> Get the new packet header stack to use it for appending an IPv4 stack after it.
        # Look for the packet header object and stack ID.
        packetHeaderStackObj = configElement.Stack.find(DisplayName='^{}'.format(packetHeaderToAdd))
        
        # 4> In order to modify the fields, get the field object
        packetHeaderFieldObj = packetHeaderStackObj.Field.find()

        return packetHeaderFieldObj
    
    
    # LogLevel: none, info, warning, request, request_response, all
    # all can be useful for debugging issues but is very verbose
    print("Starting Session...")
    session = SessionAssistant(IpAddress=apiServerIp, RestPort=None, UserName=username, Password=password, 
                               SessionName=scenarioName, SessionId=None, ApiKey=None,
                               ClearConfig=True, LogLevel=verbosity, LogFilename=outLogFile)

    ixNetwork = session.Ixnetwork
   
    print("Assigning Ports...",end="")
    ixNetwork.info('Assign ports')
    portMap = session.PortMapAssistant()
    vport = dict()
    for index,port in enumerate(portList):
        portName = 'Port_EP{}'.format(index+1)
        vport[portName] = portMap.Map(IpAddress=port[0], CardId=port[1], PortId=port[2], Name=portName)

    # Skip connecting ports, because this is just an API demo of how to generate different traffic types

    # print("Connecting Ports...")
    # portMap.Connect(forceTakePortOwnership)

    # Setup EP1
    print("Creating Topology 1 of 3...",end="")
    ixNetwork.info('Creating Topology Group 1')
    ep1_topology = ixNetwork.Topology.add(Name='EP1', Ports=vport['Port_EP1'])
    ep1_dg1 = ep1_topology.DeviceGroup.add(Name='EP1.DG1', Multiplier='1')
    ep1_eth1 = ep1_dg1.Ethernet.add(Name='EP1.DG1.Eth1')

    ep1_eth1.Mac.Single(value='00:11:01:00:00:01')

    ixNetwork.info('Configuring EP1 IP1')
    ip1 = ep1_eth1.Ipv4.add(Name='EP1.IP1')
    ip1.Address.Single(value='100.1.0.1')
    ip1.Prefix.Single(value='24')
    ip1.GatewayIp.Single(value='100.1.0.10')
    ip1.ResolveGateway.Single(False)

    # Setup EP3
    print(f"\rCreating Topology 2 of 3...",end="")

    ixNetwork.info('Creating Topology Group 3')
    ep3_topology = ixNetwork.Topology.add(Name='EP3', Ports=vport['Port_EP3'])
    ep3_dg1 = ep3_topology.DeviceGroup.add(Name='EP3.DG1', Multiplier='1')
    ep3_eth1 = ep3_dg1.Ethernet.add(Name='EP3.DG1.Eth1')
    ep3_eth1.Mac.Single(value='00:11:01:00:00:03')

    ixNetwork.info('Configuring EP3 IP3')
    ip3 = ep3_eth1.Ipv4.add(Name='EP3.IP3')
    ip3.Address.Single(value='100.1.0.3')
    ip3.Prefix.Single(value='24')
    ip3.GatewayIp.Single(value='100.1.0.10')
    ip3.ResolveGateway.Single(False) 

    ep3_eth2 = ep3_dg1.Ethernet.add(Name='EP3.DG.Eth2')
    ep3_eth2.Mac.Single(value='00:11:01:00:00:04')

    ixNetwork.info('Configuring EP3 IP4')
    ip4 = ep3_eth2.Ipv4.add(Name='EP3.IP4')
    ip4.Address.Single(value='100.1.0.4')
    ip4.Prefix.Single(value='24')
    ip4.GatewayIp.Single(value='100.1.0.10')
    ip4.ResolveGateway.Single(False) 


    # Setup EP2
    print(f"\rCreating Topology 3 of 3...")

    ixNetwork.info('Creating Topology Group 2')
    ep2_topology = ixNetwork.Topology.add(Name='EP2', Ports=vport['Port_EP2'])
    ep2_dg1 = ep2_topology.DeviceGroup.add(Name='EP2.DG1', Multiplier='1')
    ep2_eth1 = ep2_dg1.Ethernet.add(Name='EP2.DG1.Eth1')
    ep2_eth1.Mac.Single(value='00:11:01:00:00:02')

    # Setup a VLAN so we can send prioritized traffic from this endpoint
    ep2_eth1.EnableVlans.Single(True)
    vlan_properties = ep1_eth1.Vlan.find()
    vlan_properties.VlanId.Single(value='2')

    ixNetwork.info('Configuring EP2 IP2')
    ip2 = ep2_eth1.Ipv4.add(Name='EP2.IP2')
    ip2.Address.Single(value='100.1.0.2')
    ip2.Prefix.Single(value='24')
    ip2.GatewayIp.Single(value='100.1.0.10')
    ip2.ResolveGateway.Single(False)

    # Traffic item examples

    ########################################################################################################
    # Create 128 byte ethernet frames at a specified bit rate, from one ethernet stack to another
    ########################################################################################################
    ti = ixNetwork.Traffic.TrafficItem.add(Name='Ethernet 10 Kbps 128 byte frame', BiDirectional=False, TrafficType='ethernetVlan')

    # Add the source and destination.  Note that a variety of types are supported here - 
    # you can specify a topology, or a stack like ethernet or IPv4.

    # If you specify something that has multiple stacks, then you get the frames split 
    # between them which is typically not what we want.

    # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide 
    # the specific IPv4 stack you want to use.
    ti.EndpointSet.add(Sources=ep1_eth1, Destinations=ep3_eth1)

    # Note: A Traffic Item could have multiple EndpointSets (Flow groups).  Therefore, ConfigElement is a list.
    configElement = ti.ConfigElement.find()[0]

    # Configure for a particular bit rate.  By fixing frame size at 128 bytes, Keysight will determine 
    # the correct frame rate to use to achieve the specified bit rate.
    configElement.FrameRate.update(Type='bitsPerSecond', BitRateUnitsType='kbitsPerSec', Rate=10)
    configElement.FrameSize.FixedSize = 128

    # This adds Traffic Item to the Statistics Tracking field.  
    # Without this, keysight will not track frame drops, latencies, etc.
    ti.Tracking.find()[0].TrackBy = ['trackingenabled0']

    # This generates the frames based on the previous configuration.
    ti.Generate()

    ########################################################################################################
    # Create 256 byte IPv4 UDP frames at a specified line rate, from one IPv4 stack to another
    ########################################################################################################
    ti = ixNetwork.Traffic.TrafficItem.add(Name='UDP 10% line rate 256 byte frame', BiDirectional=False, TrafficType='ipv4')
    ti.EndpointSet.add(Sources=ip1, Destinations=ip4)
    configElement = ti.ConfigElement.find()[0]

    # Add the UDP packet header with appropriate destination ports.
    # Our scenarios don't care about the source port.
    udpFieldObj = createPacketHeader(ti, packetHeaderToAdd='UDP', appendToStack='IPv4')
    udpDstField = udpFieldObj.find(DisplayName='UDP-Dest-Port')
    udpDstField.Auto = False
    udpDstField.SingleValue = 1234
    
    # Configure for a particular line rate percentage.  By fixing frame size, Keysight will determine 
    # the correct frame rate to use to achieve the specified line rate.
    configElement.FrameRate.update(Type='percentLineRate', Rate=10)
    configElement.FrameSize.FixedSize = 256

    ti.Tracking.find()[0].TrackBy = ['trackingenabled0']
    ti.Generate()

    ########################################################################################################
    # Create ethernet frames at a specified frame rate, from one ethernet stack to another
    ########################################################################################################
    ti = ixNetwork.Traffic.TrafficItem.add(Name='Ethernet 1000 fps', BiDirectional=False, TrafficType='ethernetVlan')
    ti.EndpointSet.add(Sources=ep1_eth1, Destinations=ep3_eth2)
    configElement = ti.ConfigElement.find()[0]

    # Configure for a particular frame rate.  The frame rate combined with the frame size will determine the bit rate
    configElement.FrameRate.update(Type='framesPerSecond', Rate=1000)
    configElement.FrameSize.FixedSize = 128

    ti.Tracking.find()[0].TrackBy = ['trackingenabled0']
    ti.Generate()

    ########################################################################################################
    # Create ethernet frames that follow a schedule (e.g. are output at a fixed offset from the start of network cycle) with a set priority of 3
    ########################################################################################################
    ti = ixNetwork.Traffic.TrafficItem.add(Name='Ethernet 1000 fps 250us offset priority 3', BiDirectional=False, TrafficType='ethernetVlan')
    ti.EndpointSet.add(Sources=ep2_eth1, Destinations=ep3_eth1)
    configElement = ti.ConfigElement.find()[0]

    # Configure for a particular frame rate, at a fixed offset.
    configElement.FrameRate.update(Type='framesPerSecond', Rate=1000)
    configElement.FrameSize.FixedSize = 128
    configElement.TransmissionControl.update(StartDelay=250,StartDelayUnits='microseconds')

    # Set priority level
    for stack in configElement.Stack.find():
        if stack.StackTypeId == 'vlan':
            for field in stack.Field.find():
                if field.FieldTypeId == 'vlan.header.vlanTag.vlanUserPriority':
                    field.SingleValue = 3

    ti.Tracking.find()[0].TrackBy = ['trackingenabled0']
    ti.Generate()

    ########################################################################################################
    # Create 1,000,000 byte burst of ethernet frames every 10 seconds
    ########################################################################################################
    ti = ixNetwork.Traffic.TrafficItem.add(Name='Ethernet 1000000 byte burst every 10 sec', BiDirectional=False, TrafficType='ethernetVlan')
    ti.EndpointSet.add(Sources=ep1_eth1, Destinations=ep3_eth1)
    configElement = ti.ConfigElement.find()[0]

    # Configure for a burst of size 1,000,000 and period 10
    configElement.TransmissionControl.update(
        Type='custom',
        BurstPacketCount='1000',
        EnableInterBurstGap='True',
        InterBurstGap='10',
        InterBurstGapUnits='seconds'
    )
    configElement.FrameSize.update(Type='fixed', FixedSize = 1000)

    # During the burst, have the frames output as fast as possible, 100% of line rate
    configElement.FrameRate.update(Type='percentLineRate', Rate=100)

    ti.Tracking.find()[0].TrackBy = ['trackingenabled0']
    ti.Generate()



    # Cleanup

    if debugMode == False:
        for vport in ixNetwork.Vport.find():
            vport.ReleasePort()
            
        # For linux and connection_manager only
        if session.TestPlatform.Platform != 'windows':
            session.Session.remove()

except Exception as errMsg:
    print('\n%s' % traceback.format_exc(None, errMsg))
    if debugMode == False and 'session' in locals():
        if session.TestPlatform.Platform != 'windows':
            session.Session.remove()