#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "ixnetwork-restpy >= 1.7.0"
# ]
# ///
# 
"""
stream_id_scenario4_keysight.py:

   Configure Keysight for Stream Identification, Scenario 4 - IP matching
   Usage of 'nga' user on Keysight, and ports 5,6,7 are hardcoded.  Port 5 = EP1, 6 = EP2, 7 = EP3

Supports IxNetwork API servers:
   - Windows, Windows Connection Mgr and Linux

Requirements:
   - Minimum IxNetwork 8.50
   - Python 2.7 and 3+
   - pip install requests
   - pip install ixnetwork_restpy (minimum version 1.0.51)

RestPy Doc:
    https://www.openixia.github.io/ixnetwork_restpy/#/

Usage:
   - chmod +x <script.py>
   - ./<script.py>
   
"""

import sys, os, time, traceback

from ixnetwork_restpy import *

# Provide username and password to login to Keysight
username = ''
password = ''

# Provide a name for the keysight session
scenarioName = 'stream_id-4-ip_matching'

# TODO: Figure out a better / external way to provide deployment-specific information about the Keysight and the port mapping so the demo can be run with different TSN switches wired to different ports

# Our API server and chassis are same device
apiServerIp = '192.168.1.21'
chassisIp = '192.168.1.21'

# Some Keysight products have multiple slots within a single chassis, we just have 1 slot
chassisSlotNumber = 1

# Probably should have some end-point structure so each can specify a different chassisIp, slot number, and port number, making script more useful for other deployments
portNumberEP1 = 5
portNumberEP2 = 6
portNumberEP3 = 7

# Each port consists of the IP address of the chassis, the card #, and the port #
portList = [[chassisIp, chassisSlotNumber, portNumberEP1], [chassisIp, chassisSlotNumber, portNumberEP2], [chassisIp, chassisSlotNumber, portNumberEP3]]


outLogFile : str = scenarioName + '_' + time.strftime("%Y%m%d-%H%M%S") + '.log'

# For linux and connection_manager only. Set to True to leave the session alive for debugging.
debugMode = True

# Forcefully take port ownership if the portList are owned by other users.
forceTakePortOwnership = True

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
    session = SessionAssistant(IpAddress=apiServerIp, RestPort=None, UserName=username, Password=password, 
                               SessionName=scenarioName, SessionId=None, ApiKey=None,
                               ClearConfig=True, LogLevel=SessionAssistant.LOGLEVEL_INFO, LogFilename=outLogFile)

    ixNetwork = session.Ixnetwork
   
    ixNetwork.info('Assign ports')
    portMap = session.PortMapAssistant()
    vport = dict()
    for index,port in enumerate(portList):
        portName = 'Port_EP{}'.format(index+1)
        vport[portName] = portMap.Map(IpAddress=port[0], CardId=port[1], PortId=port[2], Name=portName)

    portMap.Connect(forceTakePortOwnership)

    # TODO: Figure out a better way to organize (end point class???) and consider if there is a better naming convention

    # Also, it appears that if we want specifically "talkers" on the left and "listeners" on the right in the graphical topology, 
    # we have to create the end points in order EP1, EP3, EP2.  Have not found a way to specify which side in the layout to put it, 
    # it just seems to alternate left-right-left-right.

    # Setup EP1
    ixNetwork.info('Creating Topology Group 1')
    ep1_topology = ixNetwork.Topology.add(Name='EP1', Ports=vport['Port_EP1'])
    ep1_dg1 = ep1_topology.DeviceGroup.add(Name='EP1.DG1', Multiplier='1')
    ep1_eth1 = ep1_dg1.Ethernet.add(Name='EP1.DG1.Eth1')
    ep1_eth1.Mac.Single(value='00:11:01:00:00:01')

    #   This scenario doesn't use VLANs but leaving this here so somebody starting with this, making a scenario that does use VLANs, knows where to look in the API
    #   ep1_ethernet.EnableVlans.Single(True)
    #   ixNetwork.info('Configuring vlanID')
    #   vlanObj = ep1_ethernet.Vlan.find()[0].VlanId.Increment(start_value=2, step_value=0)

    ixNetwork.info('Configuring EP1 IP1')
    ip1 = ep1_eth1.Ipv4.add(Name='EP1.IP1')
    ip1.Address.Single(value='100.1.0.1')
    ip1.Prefix.Single(value='24')
    ip1.GatewayIp.Single(value='100.1.0.10')
    ip1.ResolveGateway.Single(False)

    # Setup EP3
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
    ixNetwork.info('Creating Topology Group 2')
    ep2_topology = ixNetwork.Topology.add(Name='EP2', Ports=vport['Port_EP2'])
    ep2_dg1 = ep2_topology.DeviceGroup.add(Name='EP2.DG1', Multiplier='1')
    ep2_eth1 = ep2_dg1.Ethernet.add(Name='EP2.DG1.Eth1')
    ep2_eth1.Mac.Single(value='00:11:01:00:00:02')

    ixNetwork.info('Configuring EP2 IP2')
    ip2 = ep2_eth1.Ipv4.add(Name='EP2.IP2')
    ip2.Address.Single(value='100.1.0.2')
    ip2.Prefix.Single(value='24')
    ip2.GatewayIp.Single(value='100.1.0.10')
    ip2.ResolveGateway.Single(False)
 

    # Configure UDP Traffic items
    trafficTypeList = ['ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ethernetVlan']
    sourceList = [ep1_topology, ip1, ip1, ip1, ip2, ip2, ip2, ip2, ip2, ip2, ep1_eth1]
    destList = [ip3, ip3, ip4, ip4, ip3, ip3, ip4, ip4, ip4, ip3, ep3_eth1]
    udpList = [True, True, True, True, True, True, True, True, True, True, False]
    destPort = [1000, 1100, 2000, 2200, 3000, 3300, 4000, 4400, 5000, 5000, 0]
    txRate = [10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 19000, 20000]
    
    ixNetwork.info('Create Traffic Items')
    trafficItem = []
    for i in range(len(sourceList)):
        trafficItem.append(ixNetwork.Traffic.TrafficItem.add(Name='Traffic Item '+str(i), BiDirectional=False, TrafficType=trafficTypeList[i]))
        trafficItem[i].EndpointSet.add(Sources=sourceList[i], Destinations=destList[i])

        # Note: A Traffic Item could have multiple EndpointSets (Flow groups).  Therefore, ConfigElement is a list.
        configElement = trafficItem[i].ConfigElement.find()[0]

        if(udpList[i]):
            udpFieldObj = createPacketHeader(trafficItem[i], packetHeaderToAdd='UDP', appendToStack='IPv4')
            udpDstField = udpFieldObj.find(DisplayName='UDP-Dest-Port')
            udpDstField.Auto = False
            udpDstField.SingleValue = destPort[i]

        configElement.FrameRate.update(Type='bitsPerSecond', BitRateUnitsType='kbitsPerSec', Rate=txRate[i])
        configElement.FrameSize.FixedSize = 128
        trafficItem[i].Tracking.find()[0].TrackBy = ['trackingenabled0']

        trafficItem[i].Generate()


#    ixNetwork.Traffic.TrafficItem.Generate(trafficItem)
    ixNetwork.Traffic.Apply()
#    ixNetwork.StartAllProtocols(Arg1='sync')
    time.sleep(1)
#    ixNetwork.Traffic.StartStatelessTrafficBlocking()
    ixNetwork.Traffic.Start()
    time.sleep(1)

    flowStatistics = session.StatViewAssistant('Flow Statistics')

    # StatViewAssistant could also filter by REGEX, LESS_THAN, GREATER_THAN, EQUAL. 
    # Examples:
    #    flowStatistics.AddRowFilter('Port Name', flowStatistics.REGEX, '^Port 1$')
    #    flowStatistics.AddRowFilter('Tx Frames', flowStatistics.GREATER_THAN, "5000")

    ixNetwork.info('{}\n'.format(flowStatistics))

    for rowNumber,flowStat in enumerate(flowStatistics.Rows):
        ixNetwork.info('\n\nSTATS: {}\n\n'.format(flowStat))
        ixNetwork.info('\nRow:{}  TxPort:{}  RxPort:{}  TxFrames:{}  RxFrames:{}\n'.format(
            rowNumber, flowStat['Tx Port'], flowStat['Rx Port'],
            flowStat['Tx Frames'], flowStat['Rx Frames']))

    time.sleep(1)
    ixNetwork.Traffic.Stop()
    time.sleep(1)
    ixNetwork.Traffic.StopStatelessTrafficBlocking()
    time.sleep(1)
    ixNetwork.StopAllProtocols(Arg1='sync')
    time.sleep(1)

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