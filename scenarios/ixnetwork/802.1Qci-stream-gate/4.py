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
#from ixnetwork_restpy import SessionAssistant

import sys, os, time, traceback

from dotenv import load_dotenv

from ixnetwork_restpy import *
#from ixnetwork_restpy import SessionAssistant

from sgfunctions import basecfg

# Provide username and password to login to Keysight
load_dotenv()

# Use this snytax for linux 
username = os.getenv("IXN_USERNAME")
password = os.getenv("IXN_PASSWORD")

# Provide a name for the keysight session
scenarioName = 'stream_gate-4-gating'


try:

    [debugMode, apiServerIp, chassisIp, ixNetwork, ep1_eth2, ep2_eth2, tx_port, rx_port3] = basecfg(scenarioName, time, SessionAssistant, username, password, traceback)

    # Configure raw Traffic items.  Comments further down explain some of this.
    trafficTypeList = ['raw', 'raw', 'raw', 'raw']
    
    # Using ep1_topology just demonstrates how, if there is a single protocol stack, you can specify the entire topology,
    # and the keysight will know to use the IPv4 stack as the source since we are generating IPv4 (UDP) packets.
    # The last traffic item, we want raw ethernet frames.  
    sourceList = [ep1_eth2, ep1_eth2, ep1_eth2, ep1_eth2] # The actual sources used are the virtual ports for EP1 and EP2
    udpList = [False, False, False, False]
    frameRate = [1000, 1000, 1000, 1000]
    frameDelay = [5, 255, 505, 755]

    ixNetwork.info('Create Traffic Items')
    trafficItem = []
    vlan_outer = []
    print("Creating Traffic Item 1 of",len(sourceList),"...",end="")
    for i in range(len(sourceList)):
        print(f"\rCreating Traffic Item",1,"of",len(sourceList),"...",end="") # Want four of the same traffic item for scenario 4
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


        trafficItem.append(ixNetwork.Traffic.TrafficItem.add(
            ##Name='Traffic Item '+str(i), 
            Name='Traffic Item '+str(0), # Want four of the same traffic item for scenario 4
            TrafficType=trafficTypeList[i] #,
        ))
        
        ##endpointSet = trafficItem[i].EndpointSet.add(Sources=tx_port[i].Protocols.find(), Destinations=rx_port3.Protocols.find())
        endpointSet = trafficItem[i].EndpointSet.add(Sources=tx_port[0].Protocols.find(), Destinations=rx_port3.Protocols.find()) # Want four of the same traffic item for scenario 4
        
        #print("dir(trafficItem[i) = ", trafficItem[i])
        ##trafficItem[i].configure()
        
        # Add the Ethernet, VLAN, and IP headers to the packet stack
        configElement = trafficItem[i].ConfigElement.find()[0]
        #print("configElement.Stack.find(StackTypeId='ethernet')[0] = ", configElement.Stack.find(StackTypeId='ethernet')[0])
        
        #print("dir(configElement.Stack) = ", configElement.Stack)
        #print("dir(ixNetwork.Traffic.TrafficItem.ConfigElement) = ", ixNetwork.Traffic.TrafficItem.ConfigElement)
        #ixNetwork.traffic.trafficItem[i].configElement.stack.operations.appendProtocol(
##        VlanTagTemplate = ixNetwork.Traffic.ProtocolTemplate.find(DisplayName='^VNTAG$') # template 72 from the wb UI
        VlanTagTemplate = ixNetwork.Traffic.ProtocolTemplate.find(DisplayName='^VLAN$') # template 71 is VLAN protocol, which matches traffic item with web UI
        
        # Find the Ethernet stack in the traffic item to append the Vlan header to it
        ethernetStack = configElement.Stack.find(DisplayName='Ethernet')
        
        # Append the Vlan template to the traffic item Ethernet stack
        ethernetStack.Append(Arg2=VlanTagTemplate)
        
        #print("ethernetStack = ", ethernetStack)
        #print("dir(ethernetStack) = ", dir(ethernetStack))
        
        # Find the newly created Vlan stack object in the traffic item
        VlanTagStack = configElement.Stack.find(DisplayName='^VLAN$')[0]
                
        # Access the Field collection for the VLAN stack
        vlan_fields = VlanTagStack.Field.find()
        #print("vlan_fields = ", vlan_fields )
        
        # Find and update the specific fields

        # Find the VLAN ID field and set its value
        vlan_id_field = vlan_fields.find(DisplayName= '^VLAN Priority$') #[0]
        ##print("vlan_id_field = ", vlan_id_field)
        vlan_id_field.update(
            ##SingleValue=i+4  # Set the VLAN priority to a different values
            SingleValue=0  # Set the VLAN priority to a fixed value of 0
        )
        ##print("vlan_id_field = ", vlan_id_field)
        #print("dir(ethernetStack.Field) = ",dir(ethernetStack.Field)) ## Use this diagnostic to see the available attributes of an object

        # Attach the ethernet stacks to the corresponding MAC addresses for the endpoints
        # This one is for the destination (EP3)
        ethernetStack.Field.find(DisplayName='^Destination MAC Address$').SingleValue = '00:12:01:00:00:01'

        # This is an alternate way to find/set an Ethernet stack field (eg destination MAC for this example)
        #destination_mac = configElement.Stack.find(StackTypeId='ethernet').Field.find(FieldTypeId='ethernet.header.destinationAddress')
        #destination_mac.update(ValueType='valueList', ValueList=['00:12:01:00:00:01'])

        #print("dir(ethernetStack.Field.find(DisplayName='AvailableValueTypes')) = ",dir(ethernetStack.Field.find(DisplayName='AvailableValueTypes')))
        #print("tx_port[0].Protocols.find() = ", tx_port[0].Protocols.find()) # Want four of the same traffic item for scenario 4

        #sys.exit() # Halts the script
        
        if (i <= len(sourceList)):
            ethernetStack.Field.find(DisplayName='^Source MAC Address$').SingleValue = '00:13:01:00:00:01'
            configElement.FrameSize.FixedSize = 64
        else:
            ethernetStack.Field.find(DisplayName='^Source MAC Address$').SingleValue = '00:15:01:00:00:01'
            #print("dir(configElement.FrameSize.Type) = ",dir(configElement.FrameSize.Type))
            configElement.FrameSize.Type = 'random'
            configElement.FrameSize.RandomMin = 64
            configElement.FrameSize.RandomMax = 600

        configElement.FrameRate.update(Type='framesPerSecond', Rate=frameRate[i])
        configElement.TransmissionControl.update(StartDelayUnits = "microseconds", StartDelay = frameDelay[i])

        # If this traffic item is UDP, add the UDP packet header with appropriate destination port.
        # Our scenario doesn't care about the source port.
        if(udpList[i]):
            udpFieldObj = createPacketHeader(trafficItem[i], packetHeaderToAdd='UDP', appendToStack='IPv4')
            udpDstField = udpFieldObj.find(DisplayName='UDP-Dest-Port')
            udpDstField.Auto = False
            udpDstField.SingleValue = destPort[i]

        # Enable tracking on the VLAN User Priority field (PCP)
        # Get the tracking object for the traffic item
        trackBy = trafficItem[i].Tracking.find()


        # This adds Traffic Item to the Statistics Tracking field.  
        # Without this, keysight will not track frame drops, latencies, etc.
        trafficItem[i].Tracking.find()[0].TrackBy = ["trackingenabled0", "ethernetIiSourceaddress0", "vlanVlanUserPriority0"] # Used Firefox inspector and added Vlan tracking to get the arguments
        print("Enabled tracking on VLAN priority for the traffic item.")
        #print("dir(trafficItem[i].Tracking.find()[0].TrackBy = ", dir(trafficItem[i].Tracking.find()[0].TrackBy))

        ##sys.exit() # Halts the script

        # This generates the frames based on the previous configuration.
        trafficItem[i].Generate()
        print("Generated traffic...")

        ##sys.exit() # Halts the script
    
        
    for seq in range(2):  # Use 2 passes for scenario 4; first passes cover tests 1,2 and 2nd for tests 3,4 with anamylzer in record mode
##    for seq in range(4):  # Use for scenarios 2, 3
        # Sync to gptp time base
        # 1. Get the global Traffic object.
        GlbTraffic = ixNetwork.Traffic
        #print("dir(ixNetwork.Traffic) = ",dir(ixNetwork.Traffic))
        
        # 2. Get the transmissionControl sub-object.
        # The `useScheduledStartTransmit` setting is located under this object.
        #transmission_control = GlbTraffic.TransmissionControl
        GlbTraffic.UseScheduledStartTransmit = True
                       
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
        print("Waiting for traffic to start",end="")
        while(not ixNetwork.Traffic.IsTrafficRunning):
            print(".",end="")
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
            statsView = ixNetwork.Statistics.View.find(Caption='Flow Statistics')
            ##print('statsView = ',statsView)
            time.sleep(1.0)
            # Get the column captions (header names)
            # Get all page values (the actual statistics)
            RxRates = statsView.GetColumnValues(Arg2='Rx Frame Rate')
            VlanPriority = statsView.GetColumnValues(Arg2='VLAN:VLAN Priority')
            print('RxRates = ',RxRates)
            print('VlanPriority = ',VlanPriority)
            time.sleep(1)
        
        # time.sleep(3)
        
        statsView = ixNetwork.Statistics.View.find(Caption='Flow Statistics')
        # print(statsView)
        
        # For this scenario, success/failure is based on the receive frame rate of each traffic
        # item, matching of Tx/Rx frames to 0.1% for passed traffic and also that no frames are 
        # received when the stream gates and frames are not aligned.
        RxRates = statsView.GetColumnValues(Arg2='Rx Frame Rate')
        VlanPriority = statsView.GetColumnValues(Arg2='VLAN:VLAN Priority')
        # print("RxRates: ", RxRates)
        
        streamName = ["1", "2", "3", "4"]
        streamTrafficMembers = [0],[1],[2],[3]
        streamExpectedRxRate = [1000.0, 1000.0, 1000.0, 1000.0]
        streamRateUnits = ["Fps", "Fps", "Fps", "Fps"]
        expectedPriority = [0, 0, 0, 0, 1, 1, 2, 2]
        VlanPriorityErr = [0,0,0,0]
        
        # A tolerance needs to be applied as the Tx/Rx values may be off due to a dropped frame 
        # depending on when the traffic item is applied.
        # Using a constant tolerance of 0.1%.
        
        #print("Before stopping, scheduled_traffic_item = ", scheduled_traffic_item)
        
        longestName = len(max(streamName, key=len))
        
        for i in range(len(streamName)):
            rate = 0.0
            expectedRxRate = float(streamExpectedRxRate[i])
            tolerance = expectedRxRate * 0.01
            VlanPriorityErrTot = 0
            
            # Pad with spaces so all names are same length to make output look nice
            name = streamName[i].ljust(longestName)
            if (len(streamTrafficMembers[i]) == 0):
                emptyStream = True
            else:
                emptyStream = False
                for j in range(len(streamTrafficMembers[i])):
                    rate += float(RxRates[streamTrafficMembers[i][j]])
                    VlanPriorityErrTot += VlanPriorityErr[streamTrafficMembers[i][j]] - expectedPriority[streamTrafficMembers[i][j]]
                    print("VlanPriorityErr = ", VlanPriorityErr, "streamTrafficMembers[i][j] = ", streamTrafficMembers[i][j], "expectedPriority[streamTrafficMembers[i][j]] = ", expectedPriority[streamTrafficMembers[i][j]])
            testResult = abs(rate-expectedRxRate)<=tolerance
            testResultP = abs(VlanPriorityErrTot)==0
            if(emptyStream):
                print("N/A : Stream",name,"- scenario does not match any traffic items to this stream")
            else:
                if(testResult and testResultP):
                    print("PASS: ",end="")
                else:
                    print("FAIL: ",end="")
                print("Stream",name,"- expected rate:", expectedRxRate, streamRateUnits[i], "actual rate:", rate, streamRateUnits[i])
                
            if (VlanPriorityErrTot == 0): 
                print("VlanPriorityErrTot = ",VlanPriorityErrTot, ", PASS")
            else:
                print("VlanPriorityErrTot = ",VlanPriorityErrTot, ", FAIL")
        
        #print("Before stopping, scheduled_traffic_item = ", scheduled_traffic_item)
        
        ixNetwork.Globals.Testworkflow.Stop()
        
        time.sleep(3.0)
        TxFrames = statsView.GetColumnValues(Arg2='Tx Frames')
        RxFrames = statsView.GetColumnValues(Arg2='Rx Frames')
        ##print('TxFrames = ',TxFrames,'RxFrames = ',RxFrames)
            
        for i in range(len(TxFrames)):
            ##if(TxFrames[i]==RxFrames[i] and (i==0 or i==2)):
            if(TxFrames[i]==RxFrames[i]):
                print('Stream Row[',i,']: ', 'TxFrames = ',TxFrames[i],', RxFrames = ',RxFrames[i], "PASS: ")
            elif(float(RxFrames[i]) >  float(TxFrames[i])*0.99):
                #print('i = ', i, ' RxFrames = ', RxFrames[i])
                print('Stream Row[',i,']: ', 'TxFrames = ',TxFrames[i],', RxFrames = ',RxFrames[i], "PASS: ")
            else:
                print('Stream Row[',i,']: ', 'TxFrames = ',TxFrames[i],', RxFrames = ',RxFrames[i], "FAIL: ")
        
        
        ## Modify traffic item start times and rerun
        frameDelay = [6, 256, 506, 756, 6, 256, 506, 756] # No timing changes for PSFP scenario 3
        ##print("Change traffic packet size for stream 2")        
        for m in range(len(sourceList)):
            ##print("4*(seq+1)+m = ", 4*(seq+1)+m)
            if ((4*(seq+1)+m) < len(expectedPriority)):
                print(f"\rUpdating Vlan priority for Traffic Item",m+1,"of",len(sourceList)," to VLAN priority = ", expectedPriority[4*(seq+1)+m]," ",end="")
            if ((4*(seq+1)+m) < len(expectedPriority)):
                configElement = trafficItem[m].ConfigElement.find()[0]
                # Find the previously Vlan stack object in the mth traffic item
                VlanTagStack = configElement.Stack.find(DisplayName='^VLAN$')[0]
                # Access the Field collection for the VLAN stack
                vlan_fields = VlanTagStack.Field.find()
                #configElement.TransmissionControl.update(StartDelayUnits = "microseconds", StartDelay = frameDelay[2*seq+m])
                # Find the VLAN ID field and set its value
                vlan_id_field = vlan_fields.find(DisplayName= '^VLAN Priority$') #[0]
                ##print("vlan_id_field = ", vlan_id_field)
                vlan_id_field.update(
                    ##SingleValue=i+4  # Set the VLAN priority to a different values
                    SingleValue= expectedPriority[4*(seq+1)+m]  # Set the VLAN priority values to the secod set in expectedPriority
                )
                ##print("vlan_id_field = ", vlan_id_field)

            if (seq == 1 and m == 1):
                configElement.FrameSize.Type = 'fixed'
                configElement.FrameSize.FixedSize = 64
            # This adds Traffic Item to the Statistics Tracking field.  
            # Without this, keysight will not track frame drops, latencies, etc.
            trafficItem[m].Tracking.find()[0].TrackBy = ["trackingenabled0", "ethernetIiSourceaddress0", "vlanVlanUserPriority0"]
            # This generates the frames based on the previous configuration.
            trafficItem[m].Generate()
            print("Generated updated traffic...")
        
        # Pause the script to change the switch configuration as needed        
        SW_status = input("If needed, update the TSN switch now ")
        print(f"Switch status, {SW_status}!")

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