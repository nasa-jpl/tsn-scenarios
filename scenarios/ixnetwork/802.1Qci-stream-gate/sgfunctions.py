# This Function handles the template generation, API session, virtual ports and EPs
# for stream gate scenarios 1-4

from ixnetwork_restpy import *

ep1_eth2 = "global_value"        
ep2_eth2 = "global_value"   
debugMode = "global_value" 
SessionAssistant = "global_value" 
session = "global_value" 
Ixnetwork = "global_value" 
ixNetwork = "global_value" 
tx_port = "global_value"
rx_port3 = "global_value"

def basecfg(scenarioName, time, SessionAssistant, username, password, traceback):
    global ep1_eth2, ep2_eth2
    # Our API server and chassis are same device
    apiServerIp = '192.168.1.21'
    chassisIp = '192.168.1.21'
    
    # Some Keysight products have multiple slots within a single chassis, we just have 1 slot
    chassisSlotNumber = 1
    
    # Probably should have some end-point structure so each can specify a different chassisIp, slot number, and port number, making script more useful for other deployments
    portNumberEP1 = 1
    portNumberEP2 = 2
    portNumberEP3 = 4
    
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
        # The def block sets up a blank packet header, brings in protocol templates and 
        # appends a blank template to the stack; these methods are used in the code below.
        # The def block can be commented out and the code still functions the same way
        def createPacketHeader(trafficItemObj, packetHeaderToAdd=None, appendToStack=None): 
            configElement = trafficItemObj.ConfigElement.find()
    
            # Do the followings to add packet headers on the new traffic item
    
            # Get a list of all the available protocol templates to create (packet headers)
            availableProtocolTemplates = []
            for protocolHeader in ixNetwork.Traffic.ProtocolTemplate.find():
                availableProtocolTemplates.append(protocolHeader.DisplayName)
            
            print("availableProtocolTemplates =", availableProtocolTemplates)
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
        # 1. Connect to IxNetwork:SM 8/12/25 *****************
        session = SessionAssistant(IpAddress=apiServerIp, RestPort=None, UserName=username, Password=password, 
                                   SessionName=scenarioName, SessionId=None, ApiKey=None,
                                   ClearConfig=True, LogLevel=verbosity, LogFilename=outLogFile)
    
        ixNetwork = session.Ixnetwork
        
        
        # 2. Add Virtual Ports:SM 8/12/25 *****************
        print("Assigning Ports...",end="")
        ixNetwork.info('Assign ports')
        # Assign ports
        portMap = session.PortMapAssistant()
        vport = dict()
        for index,port in enumerate(portList):
            portName = 'Port_EP{}'.format(index+1)
            vport[portName] = portMap.Map(IpAddress=port[0], CardId=port[1], PortId=port[2], Name=portName)
            print("vport[portName]= ",vport[portName])
    
        print("Connecting Ports...")
        portMap.Connect(forceTakePortOwnership)
    
        tx_port = [1,2,3,4,5]
        # Get port objects
        tx_port[0] = ixNetwork.Vport.find(Name='Port_EP1')
        tx_port[1] = ixNetwork.Vport.find(Name='Port_EP2')
        rx_port3 = ixNetwork.Vport.find(Name='Port_EP3')
    
        # TODO: Figure out a better way to organize (end point class???) and consider if there is a better naming convention
    
        # Also, it appears that if we want specifically "talkers" on the left and "listeners" on the right in the graphical topology, 
        # we have to create the end points in order EP1, EP3, EP2.  Have not found a way to specify which side in the layout to put it, 
        # it just seems to alternate left-right-left-right.
    
        # Setup EP1
        # To send or receive data on a port on Keysight, you need a 'topology' which contains 1 or more 'device groups' 
        # which contains 1 or more 'protocol stacks'.  The protocol stacks for TSN scenarios always start with Ethernet.
        # If using raw ethernet (with or without VLANs), that is all that is needed.  If using IPv4, that is added on top of the Ethernet.
        # 3. Create a Device Group and Add Ethernet and gPTP protocols:SM 8/12/25 *****************
        print("Creating Topology 1 of 3...",end="")
        ixNetwork.info('Creating Topology Group 1')
        ep1_topology = ixNetwork.Topology.add(Name='EP1', Ports=vport['Port_EP1'])
        ep1_dg1 = ep1_topology.DeviceGroup.add(Name='EP1.DG1', Multiplier='1')
        # Add Ethernet protocol
        ep1_eth1 = ep1_dg1.Ethernet.add(Name='EP1.DG1.Eth1')
        # Note that there are are certain uses for some of the upper bits of MAC address.  Recommend always using 00 for the most significant 8 bits.
        ep1_eth1.Mac.Increment(start_value="00:11:01:00:00:01", step_value="00:00:00:00:00:01")
       
        # Add gPTP protocol on top of Ethernet:SM 8/12/25
        ixNetwork.info('Configuring EP1 PTP1')
        ep1_eth1_ptp1 = ep1_eth1.Ptp.add()
        ep1_eth1_ptp1.Role.Single("master")           # Set PTP1 to grandmaster:SM 8/13/25
        ep1_eth1_ptp1.Profile.Single("ieee8021asrev") # Set PTP1 to proper ptp protocol:SM 8/13/25
    
    
        # Create a second Ethernet group with VLAN access:SM 8/12/2025
        # Add Ethernet protocol:SM 8/12/2025
        ep1_eth2 = ep1_dg1.Ethernet.add(Name='EP1.DG1.Eth2')
        #ep1_eth2.Mac.Single(value='00:13:01:00:00:01')
        ep1_eth2.Mac.Increment(start_value="00:13:01:00:00:01", step_value="00:00:00:00:00:01")
        ep1_eth2.EnableVlans.Single(True)
        ep1_eth2.UseVlans = True
        ep1_eth2.VlanCount = 1
        
        
        # Setup EP3
        # For this scenario there are 2 separate stacks with separate MAC addresses for sources and one for the destination
        print(f"\rCreating Topology 2 of 3...",end="")
        ixNetwork.info('Creating Topology Group 3')
        ep3_topology = ixNetwork.Topology.add(Name='EP3', Ports=vport['Port_EP3'])
        ep3_dg1 = ep3_topology.DeviceGroup.add(Name='EP3.DG1', Multiplier='1')
        # Add Ethernet protocol
        ep3_eth1 = ep3_dg1.Ethernet.add(Name='EP3.DG1.Eth1')
    
        # Note that there are are certain uses for some of the upper bits of MAC address.  Recommend always using 00 for the most significant 8 bits.
        ep3_eth1.Mac.Increment(start_value="00:12:01:00:00:01", step_value="00:00:00:00:00:01")
        
        # Add gPTP protocol on top of Ethernet:SM 8/12/25
        ixNetwork.info('Configuring EP3 PTP1')
        ep3_eth1_ptp1 = ep3_eth1.Ptp.add()
        ep3_eth1_ptp1.Role.Single("slave")           # Set PTP1 to grandmaster:SM 8/13/25
        ep3_eth1_ptp1.Profile.Single("ieee8021asrev") # Set PTP1 to proper ptp protocol:SM 8/13/25
    
    
    
        # Setup EP2
        print(f"\rCreating Topology 3 of 3...")
        ixNetwork.info('Creating Topology Group 2')
        ep2_topology = ixNetwork.Topology.add(Name='EP2', Ports=vport['Port_EP2'])
        ep2_dg1 = ep2_topology.DeviceGroup.add(Name='EP2.DG1', Multiplier='1')
        # Add Ethernet protocol
        ep2_eth1 = ep2_dg1.Ethernet.add(Name='EP2.DG1.Eth1')
    
        # Note that there are are certain uses for some of the upper bits of MAC address.  Recommend always using 00 for the most significant 8 bits.
        #ep2_eth1.Mac.Single(value='00:14:01:00:00:01')
        ep2_eth1.Mac.Increment(start_value="00:14:01:00:00:01", step_value="00:00:00:00:00:01")
        
        
        # Add gPTP protocol on top of Ethernet:SM 8/12/25
        ixNetwork.info('Configuring EP2 PTP1')
        ep2_eth1_ptp1 = ep2_eth1.Ptp.add()
        ep2_eth1_ptp1.Role.Single("slave")           # Set PTP1 to grandmaster:SM 8/13/25
        ep2_eth1_ptp1.Profile.Single("ieee8021asrev") # Set PTP1 to proper ptp protocol:SM 8/13/25
    
        # Create a second Ethernet group with VLAN access:SM 8/12/2025
        # Add Ethernet protocol:SM 8/12/2025
        ep2_eth2 = ep2_dg1.Ethernet.add(Name='EP2.DG1.Eth2')
        ep2_eth2.Mac.Increment(start_value="00:15:01:00:00:01", step_value="00:00:00:00:00:01")
        ep2_eth2.EnableVlans.Single(True)
        ep2_eth2.UseVlans = True
        ep2_eth2.VlanCount = 1

        #config_list = [debugMode, ep1_eth2, ep2_eth2]

    except Exception as errMsg:
        print('\n%s' % traceback.format_exc(None, errMsg))
        if debugMode == False and 'session' in locals():
            if session.TestPlatform.Platform != 'windows':
                session.Session.remove()
                
    return debugMode, apiServerIp, chassisIp, ixNetwork, ep1_eth2, ep2_eth2, tx_port, rx_port3
