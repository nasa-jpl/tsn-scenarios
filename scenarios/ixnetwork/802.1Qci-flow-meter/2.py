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

# Provide a name for the keysight session
scenarioName = 'flow_meter-2'

# Our API server and chassis are same device
apiServerIp = '192.168.1.21'
chassisIp = '192.168.1.21'

# Some Keysight products have multiple slots within a single chassis, we just have 1 slot
chassisSlotNumber = 1

# Probably should have some end-point structure so each can specify a different chassisIp, slot number, and port number, making script more useful for other deployments
portNumberEP1 = 1
portNumberEP2 = 2
portNumberEP3 = 3

# Each port consists of the IP address of the chassis, the card #, and the port #
portList = [[chassisIp, chassisSlotNumber, portNumberEP1], [chassisIp, chassisSlotNumber, portNumberEP2], [chassisIp, chassisSlotNumber, portNumberEP3]]


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

    print("Connecting Ports...")
    portMap.Connect(forceTakePortOwnership)

    # It appears that if we want specifically "talkers" on the left and "listeners" on the right in the graphical topology, 
    # we have to create the end points in order EP1, EP3, EP2.  Have not found a way to specify which side in the layout to put it, 
    # it just seems to alternate left-right-left-right.

    # Setup EP1
    # To send or receive data on a port on Keysight, you need a 'topology' which contains 1 or more 'device groups' 
    # which contains 1 or more 'protocol stacks'.  The protocol stacks for TSN scenarios always start with Ethernet.
    # If using raw ethernet (with or without VLANs), that is all that is needed.  If using IPv4, that is added on top of the Ethernet.
    print("Creating Topology 1 of 3...",end="")
    ixNetwork.info('Creating Topology Group 1')
    ep1_topology = ixNetwork.Topology.add(Name='EP1', Ports=vport['Port_EP1'])
    ep1_dg1 = ep1_topology.DeviceGroup.add(Name='EP1.DG1', Multiplier='1')
    ep1_eth1 = ep1_dg1.Ethernet.add(Name='EP1.DG1.Eth1')

    # Note that there are are certain uses for some of the upper bits of MAC address.  Recommend always using 00 for the most significant 8 bits.
    ep1_eth1.Mac.Single(value='00:11:01:00:00:01')

    # This scenario doesn't use VLANs but leaving this here so somebody starting with this, 
    # making a scenario that does use VLANs, knows where to look in the API

    # ep1_eth1.EnableVlans.Single(True)
    # ep1_eth1_vlan = ep1_eth1.Vlan.find()[0].VlanId.SingleValue(2)

    # For IPv4, specify an IP address on the same subnet as the Gateway (by setting prefix to 24, and using the same first 3 numbers x.y.z.*)
    # The Gateway does not need to exist, but keysight will not generate traffic correctly otherwise
    # Resolve Gateway needs to be deselected so the keysight does not try to actually access the gateway
    ixNetwork.info('Configuring EP1 IP1')
    ip1 = ep1_eth1.Ipv4.add(Name='EP1.IP1')
    ip1.Address.Single(value='100.1.0.1')
    ip1.Prefix.Single(value='24')
    ip1.GatewayIp.Single(value='100.1.0.10')
    ip1.ResolveGateway.Single(False)

    # Setup EP3
    # For this scenario there are 2 separate stacks with separate IP addresses
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


    # Setup EP2
    print(f"\rCreating Topology 3 of 3...")

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
 

    # Configure UDP Traffic items.  Comments further down explain some of this.
    trafficTypeList = ['ipv4', 'ipv4'] # , 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ipv4', 'ethernetVlan']
    
    # Using ep1_topology just demonstrates how, if there is a single protocol stack, you can specify the entire topology,
    # and the keysight will know to use the IPv4 stack as the source since we are generating IPv4 (UDP) packets.
    # The last traffic item, we want raw ethernet frames.  
    sourceList = [ep1_topology, ep2_topology] 
    destList = [ep3_topology, ep3_topology] 
    udpList = [True, True] 
    destPort = [1000, 1100] 
    txRate = [1000, 1000, 980000, 980000] # Rates alternate between traffic items 1 and 2 

    # --- Burst Configuration ---
    burst_gap_duration_ms = [499.9, 49.9, 499.9, 49.9]  # The inter-burst gap duration in milliseconds (500ms - 0.1ms) = 499.9ms
    BURST_SIZE_PACKETS = 500 # Burst size in bits is #pkts/brst*#btyes/pkt*#bits/byte = 10000*100*8 = 8,000,000 bits

    ixNetwork.info('Create Traffic Items')
    trafficItem = []
    print("Creating Traffic Item 1 of",len(sourceList),"...",end="")
    for i in range(len(sourceList)):
        print(f"\rCreating Traffic Item",i+1,"of",len(sourceList),"...",end="")
        # Create a traffic item.  This scenario, all traffic is uni-directional.  
        # Need to specify the type so that the appropriate packet headers are applied.
        trafficItem.append(ixNetwork.Traffic.TrafficItem.add(Name='Traffic Item '+str(i), BiDirectional=False, TrafficType=trafficTypeList[i]))

        # Add the source and destination.  Note that a variety of types are supported here - 
        # you can specify a topology, or a stack like ethernet or IPv4.

        # If you specify something that has multiple stacks, then you get the frames split 
        # between them which is typically not what we want.

        # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide 
        # the specific IPv4 stack you want to use.
        trafficItem[i].EndpointSet.add(Sources=sourceList[i], Destinations=destList[i])

        # Note: A Traffic Item could have multiple EndpointSets (Flow groups).  Therefore, ConfigElement is a list.
        configElement = trafficItem[i].ConfigElement.find()[0]

        # Rest_py template # 71 is VLAN protocol which matches traffic item with web UI
        VlanTagTemplate = ixNetwork.Traffic.ProtocolTemplate.find(DisplayName='^VLAN$')

        # Find the Ethernet stack in the traffic item to append the Vlan header to it
        ethernetStack = configElement.Stack.find(DisplayName='Ethernet')
        
        # Add the Ethernet, VLAN, and VLAN headers to the packet stack
        # Append the Vlan template to the traffic item Ethernet stack
        ethernetStack.Append(Arg2=VlanTagTemplate)
        print("ethernetStack = ", ethernetStack)
        
        # Find the newly created Vlan stack object in the traffic item
        VlanTagStack = configElement.Stack.find(DisplayName='^VLAN$')[0]

        # Access the Field collection for the VLAN stack
        vlan_fields = VlanTagStack.Field.find()

        # Find the VLAN ID field and set its value
        vlan_id_field = vlan_fields.find(DisplayName= '^VLAN Priority$')
        print("vlan_id_field = ", vlan_id_field)
        vlan_id_field.update(
            SingleValue=0  # Set the VLAN priority to a fixed value of 0
        )
        print("vlan_id_field = ", vlan_id_field)
        
        # If this traffic item is UDP, add the UDP packet header with appropriate destination port.
        # Our scenario doesn't care about the source port.
        if(udpList[i]):
            udpFieldObj = createPacketHeader(trafficItem[i], packetHeaderToAdd='UDP', appendToStack='IPv4')
            udpDstField = udpFieldObj.find(DisplayName='UDP-Dest-Port')
            udpDstField.Auto = False
            udpDstField.SingleValue = destPort[i]

        # Configure for a particular bit rate by setting the packet size in bytes and the packet rate.
        configElement.FrameSize.FixedSize = 2000

        print("i = ", i)
        if (i==0): # This case is for traffic item 1
            # Set the Inter-Burst Gap. The gap is configured in the `FrameRate` object.
            # The type must be set to `interBurstGap` and the value provided in nanoseconds.
            configElement.FrameRate.update(
                Type='pps',
                Rate=2              # 2 packets per second
            )

            # Set the transmission mode to 'custom' to enable specific burst settings
            # In the GUI, this might correspond to 'Burst' or similar transmission mode
            configElement.TransmissionControl.update(
                Type='custom', 
                **{
                    'BurstPacketCount': BURST_SIZE_PACKETS,    # Number of packets per burst
                    'InterBurstGap': burst_gap_duration_ms[i], # Inter-burst gap in nanoseconds (e.g., 1ms = 1,000,000 ns)
                    'InterBurstGapUnits': 'milliseconds',      # Units can be 'nanoseconds', 'microseconds', 'milliseconds', 'seconds'
                    'StartDelay': 0,                           # Start delay before the first burst
                    'MinGapBytes': 12,                         # Minimum gap between packets *within* a burst (optional, typically default)
                    'EnableInterBurstGap': True                # Explicitly enable the feature (if required by API version)
                }
            )

            # 4. Set the bit rate for the burst.
            # Example: Send the burst at a percentage of line rate
            configElement.FrameRate.update(Type='percentLineRate', Rate=100)
            
            # Set the gap between bursts in milliseconds
            # For example, a 500ms gap between bursts
            configElement.TransmissionControl.update(InterBurstGap=burst_gap_duration_ms[i])
        else: # This case is for traffic item 2; set this traffic item as a continuous item.
            configElement.FrameRate.update(Type='Continuous')
            configElement.FrameRate.update(Type='bitsPerSecond', BitRateUnitsType='kbitsPerSec', Rate=txRate[i])
       
        # This adds Traffic Item to the Statistics Tracking field.  
        # Without this, keysight will not track frame drops, latencies, etc.
        trafficItem[i].Tracking.find()[0].TrackBy = ["ethernetIiSourceaddress0", 'trackingenabled0']
        # This generates the frames based on the previous configuration.
        trafficItem[i].Generate()
    print()

    num_passes = 4
    # This is the loop used to run four test cases for flow meter escenario 2; four passes are needed
    for seq in range(num_passes):    
        # Get the global Traffic object.
        GlbTraffic = ixNetwork.Traffic
        
        # arg2 = True means to forcefully grab the ports
        # Note that this is non-blocking, but any further operation that relies on the traffic will block until the traffic is started
        print("Starting traffic...")
        ixNetwork.Globals.Testworkflow.Start(arg2=True)
        
        # Wait until traffic is running
        print("Waiting for traffic to start",end="")
        while(not ixNetwork.Traffic.IsTrafficRunning):
            print(".",end="")
            time.sleep(2.0)
        print()
        
        # Wait additional time because if we grab traffic stats instantly, the switch won't have had an 
        # opportunity to do the flow metering, and it can take a little while for the keysight stats 
        # "moving average" to not reflect the startup transient
        time.sleep(12.0)
        
        RxRatesFl = []
        RxRateAcc = 0
        RxSampleNum = 10

        print("Waiting for statistics to settle...")
        print("  TxRates  ", "              RxRates")
        for i in range(RxSampleNum):
            statsView = ixNetwork.Statistics.View.find(Caption='Flow Statistics')
            RxRates = statsView.GetColumnValues(Arg2='Rx Rate (bps)')
            TxRates = statsView.GetColumnValues(Arg2='Tx Rate (bps)')
            print(TxRates, RxRates)
            RxRatesFl.append([float(s) for s in RxRates])
            time.sleep(1)

        column_index = 0  # Index of the column values for traffic item 0 to sum
        RxRateAcc = sum(row[column_index] for row in RxRatesFl if column_index < len(row)) # Add 1st column of elemets in list of lists (i.e. Traffic item 0)
        column_index = 1  # Index of the column values for traffic item 1 to sum
        RxRateAccCt = sum(row[column_index] for row in RxRatesFl if column_index  < len(row)) # Add 2nd column of elemets in list of lists (i.e. Traffic item 1)
        RxRateAve = RxRateAcc/RxSampleNum
        RxRateAveCt = RxRateAccCt/RxSampleNum
        print("RxRateAve = ", RxRateAve, ", RxRateAveCt = ", RxRateAveCt)

    
        statsView = ixNetwork.Statistics.View.find(Caption='Flow Statistics')
        # print(statsView)
    
        # For this scenario, success/failure is based on the receive bit rate of each traffic
        # item to see that the flow meter is applied by the switch.
        streamName = ["1", "2"]
        streamTrafficMembers = [0],[1]
        streamExpectedRxRate = [16000000.0, 110000000.0, 16000000.0, 110000000.0]
        streamExpectedRxRateCt = [1000000.0, 1000000.0, 980000000.0, 980000000.0]
        streamRateUnits = ["bps", "bps", "bps", "bps"]
    
        # A tolerance needs to be applied as the values won't be exact based on how the flow meter is applied.
        # Currently, there seems to be some source of error we have not figured out, so the tolerance
        # needs to be a bit higher than ideal.  For example, a flow restricted to 5000 Kbps we might see 5020 Kbps.
        # The error seems to be more a constant than a ratio of the traffic, so a flow restricted to 100 Kbps might see 120 Kbps.
        # For now, using a constant tolerance of 2% but that might not work for scenarios using lower flow meter rates.
    
        longestName = len(max(streamName, key=len))
    
        for i in range(len(streamName)):
            if (i == 0): # Burst stream statistics
                rate = 0.0
                expectedRxRate = float(streamExpectedRxRate[i+seq])
                tolerance = expectedRxRate * 0.02
                
                # Pad with spaces so all names are same length to make output look nice
                name = streamName[i].ljust(longestName)
                if (len(streamTrafficMembers[i]) == 0):
                    emptyStream = True
                else:
                    emptyStream = False
                    for j in range(len(streamTrafficMembers[i])):
                        rate += float(RxRates[streamTrafficMembers[i][j]])
                testResult = abs(RxRateAve-expectedRxRate)<=tolerance
                print("testResult = ", testResult)
                if(emptyStream):
                    print("N/A : Stream",name,"- scenario does not match any traffic items to this stream")
                else:
                    if(testResult):
                        print("PASS: ",end="")
                    else:
                        print("FAIL: ",end="")
                    print("Stream",name,"- expected rate:", expectedRxRate, streamRateUnits[i], "actual average rate:", RxRateAve, streamRateUnits[i])
            elif (i == 1): # Continuous stream statistics
                rate = 0.0
                expectedRxRate = float(streamExpectedRxRateCt[seq])
                tolerance = expectedRxRate * 0.02
                
                # Pad with spaces so all names are same length to make output look nice
                name = streamName[i].ljust(longestName)
                if (len(streamTrafficMembers[i]) == 0):
                    emptyStream = True
                else:
                    emptyStream = False
                    for j in range(len(streamTrafficMembers[i])):
                        rate += float(RxRates[streamTrafficMembers[i][j]])
                if (seq < num_passes-1):
                    testResult = abs(RxRateAveCt-expectedRxRate)<=tolerance
                else:
                    testResult = True # This case depends on how the flow meter DEI bit is treated; so call it "true" for now
                print("testResult = ", testResult)
                if(emptyStream):
                    print("N/A : Stream",name,"- scenario does not match any traffic items to this stream")
                else:
                    if(testResult):
                        print("PASS: ",end="")
                    else:
                        print("FAIL: ",end="")
                    print("Stream",name,"- expected rate:", expectedRxRate, streamRateUnits[i], "actual average rate:", RxRateAveCt, streamRateUnits[i])
        
        time.sleep(1.0)
        ixNetwork.Globals.Testworkflow.Stop()
        time.sleep(1.0)
    
    
        print("Change traffic burst interval time")        
        for m in range(len(sourceList)):
            #print("m = ", m)
            configElement = trafficItem[m].ConfigElement.find()[0]
            if (m == 0 and seq <3):
                print(f"\rUpdating burst interval time for Traffic Item",seq+1,"of",len(sourceList)," to InterBurstGap = ", burst_gap_duration_ms[seq+1]," ",end="\n")
                configElement.TransmissionControl.update(
                    Type='custom', 
                    **{
                        #'BurstPacketCount': BURST_SIZE_PACKETS,      # Number of packets per burst
                        'InterBurstGap': burst_gap_duration_ms[seq+1]   # Inter-burst gap in nanoseconds (e.g., 1ms = 1,000,000 ns)
                        #'InterBurstGapUnits': 'milliseconds',        # Units can be 'nanoseconds', 'microseconds', 'milliseconds', 'seconds'
                        #'StartDelay': 0,                             # Start delay before the first burst
                        #'MinGapBytes': 12,                           # Minimum gap between packets *within* a burst (optional, typically default)
                        #'EnableInterBurstGap': True                  # Explicitly enable the feature (if required by API version)
                    }
                )
            elif(m == 1  and seq <3):
                #print("seq = ", seq, " , txRate[seq+1] = ", txRate[seq+1], " Kbps")
                print("Updating traffic item 2 txRate to ", txRate[seq+1], " Kbps")
                configElement.FrameRate.update(Type='bitsPerSecond', BitRateUnitsType='kbitsPerSec', Rate=txRate[seq+1])


        # Pause the script to change the switch configuration as needed        
        SW_status = input("If needed, update the TSN switch now ")
        print(f"Switch status, {SW_status}!")

        # This adds Traffic Item to the Statistics Tracking field.  
        # Without this, keysight will not track frame drops, latencies, etc.
        trafficItem[m].Tracking.find()[0].TrackBy = ["ethernetIiSourceaddress0", 'trackingenabled0']
        time.sleep(1.0)
        if (seq < (num_passes-1)):
            if (m < len(sourceList)):
                # This generates the frames based on the previous configuration.
                trafficItem[m].Generate()
                print("Generated updated traffic...")

    print("********Done running tests********")        


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