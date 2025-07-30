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

# For Linux API server only
username = 'nga'
password = 'uya*mau8YAD7wkw-vgx'

outLogFile : str = scenarioName + '_' + time.strftime("%Y%m%d-%H%M%S") + '.log'

# For linux and connection_manager only. Set to True to leave the session alive for debugging.
debugMode = True

# Forcefully take port ownership if the portList are owned by other users.
forceTakePortOwnership = True

try:
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
    ep1_deviceGroup = ep1_topology.DeviceGroup.add(Name='EP1.DG', Multiplier='1')
    ep1_ethernet = ep1_deviceGroup.Ethernet.add(Name='EP1.DG.Eth1')
    ep1_ethernet.Mac.Single(value='00:11:01:00:00:01')

 #   This scenario doesn't use VLANs but leaving this here so somebody starting with this, making a scenario that does use VLANs, knows where to look in the API
 #   ep1_ethernet.EnableVlans.Single(True)
 #   ixNetwork.info('Configuring vlanID')
 #   vlanObj = ep1_ethernet.Vlan.find()[0].VlanId.Increment(start_value=2, step_value=0)

    ixNetwork.info('Configuring EP1 IPv4 1')
    ep1_ipv4_1 = ep1_ethernet.Ipv4.add(Name='EP1.IPv4-1')
    ep1_ipv4_1.Address.Single(value='100.1.0.1')
    ep1_ipv4_1.Prefix.Single(value='24')
    ep1_ipv4_1.GatewayIp.Single(value='100.1.0.10')
    ep1_ipv4_1.ResolveGateway.Single(False)

# Setup EP2
    ixNetwork.info('Creating Topology Group 2')
    ep2_topology = ixNetwork.Topology.add(Name='EP2', Ports=vport['Port_EP2'])
    ep2_deviceGroup = ep2_topology.DeviceGroup.add(Name='EP2.DG', Multiplier='1')
    ep2_ethernet = ep2_deviceGroup.Ethernet.add(Name='EP2.DG.Eth1')
    ep2_ethernet.Mac.Single(value='00:11:01:00:00:02')

    ixNetwork.info('Configuring EP2 IPv4 1')
    ep2_ipv4_1 = ep2_ethernet.Ipv4.add(Name='EP2.Ipv4-1')
    ep2_ipv4_1.Address.Single(value='100.1.0.2')
    ep2_ipv4_1.Prefix.Single(value='24')
    ep2_ipv4_1.GatewayIp.Single(value='100.1.0.10')
    ep2_ipv4_1.ResolveGateway.Single(False)
 
# Setup EP3
    ixNetwork.info('Creating Topology Group 3')
    ep3_topology = ixNetwork.Topology.add(Name='EP3', Ports=vport['Port_EP3'])
    ep3_deviceGroup = ep3_topology.DeviceGroup.add(Name='EP3.DG', Multiplier='1')
    ep3_ethernet = ep3_deviceGroup.Ethernet.add(Name='EP3.DG.Eth1')
    ep3_ethernet.Mac.Single(value='00:11:01:00:00:03')

    ixNetwork.info('Configuring EP3 IPv4 1')
    ep3_ipv4_1 = ep3_ethernet.Ipv4.add(Name='EP3.Ipv4-1')
    ep3_ipv4_1.Address.Single(value='100.1.0.3')
    ep3_ipv4_1.Prefix.Single(value='24')
    ep3_ipv4_1.GatewayIp.Single(value='100.1.0.10')
    ep3_ipv4_1.ResolveGateway.Single(False) 


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