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
        """This function is used to create packet headers that can then be manipulated by the caller"""

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

    def _validate_traffic_endpoint(self, traffic_endpoint):
        """Takes in an endpoint of the form <EP>.<DG>.<protocol_stack>
        and makes sure that the corresponding endpoint is in the topology"""
        keys = traffic_endpoint.split(".")

        # Check endpoint name and device_group
        if self._endpoints.get(keys[0], False) == False:
            raise RuntimeError(f'{keys[0]} not a valid endpoint in toplogy')

        if self._endpoints[keys[0]].get("device_groups", False) == False:
            raise RuntimeError(
                f'{keys[0]} does not contain a device_groups in toplogy')

        eps = self._endpoints[keys[0]]["device_groups"]
        for key in keys[1:-1]:
            if key not in eps:
                raise RuntimeError(f'{traffic_endpoint} not a valid endpoint')
            eps = eps["key"]

    def _validate_configs(self):
        """Takes in the endpoints and traffic_items read from the yaml files and validates them"""

        # Make sure each src and dst lists match in size, and have a corresponding endpoint
        for traffic_item in self._traffic_items.items():
            if not isinstance(traffic_item["src"], list):
                raise RuntimeError(
                    f'Traffic source {traffic_item["src"]} must be a list')

            if not isinstance(traffic_item["dst"], list):
                raise RuntimeError(
                    f'Traffic source {traffic_item["dst"]} must be a list')

            if len(traffic_item["src"]) != len(traffic_item["dst"]):
                raise RuntimeError(
                    f'Traffic src and dst list sizes must match')

            for traffic_endpoint in traffic_item["src"]:
                self._validate_traffic_endpoint(traffic_endpoint)

            for traffic_endpoint in traffic_item["dst"]:
                self._validate_traffic_endpoint(traffic_endpoint)

    def create_session(self,
                       topology_file,
                       traffic_file,
                       log_file,
                       debug_mode=False,
                       force_take_port_ownership=True,
                       verbosity=SessionAssistant.LOGLEVEL_NONE):
        """Creates a session with ixnetwork_restpy"""
        # Forcefully take port ownership if the portList are owned by other users.
        self._force_take_port_ownership = True

        # How verbose do we want the output
        self._verbosity = SessionAssistant.LOGLEVEL_NONE
        self._debug_mode = debug_mode

        self._logfile = log_file

        session_name = os.path.basename(log_file)
        session_name, _ = os.path.splitext(session_name)
        self._session_name = session_name

        # Load endpoints and traffic items
        self._endpoints = yaml.load_safe(toplogy_file)
        self._traffic_items = yaml.load_safe(traffic_file)
        self._validate_configs()

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
        ix_endpoints = dict()
        for name, endpoint in self._endpoints.items():

            print(f'Creating {name} topology...', end='')
            # Go through all device groups in this endpoint
            for i, device_group_name in enumerate(endpoint["device_groups"],
                                                  start=1):
                ix_network.info(f'Creating {name} topology device group {i}')
                topologies[name] = ix_network.Topology.add(Name=name,
                                                           Ports=vport[name])
                ix_endpoints[name] = topologies[name]
                ix_group = topologies[name].DeviceGroup.add(
                    Name=f'{name}.DG{i}', Multiplier='1')
                ix_endpoints[f"{name}.{device_group_name}"] = ix_group
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
                        if eth_stack["ipv4"] == True:
                            ix_network.info(f'Configuring {name} IP{j}')
                            ipv4 = ix_eth.Ipv4.add(Name=f'{name}.IP{j}')
                            ipv4.Address.Single(value=eth_stack["ip"])
                            ipv4.Prefix.Single(
                                value=str(eth_stack["gateway_prefix"]))

                            # We assume the gateway prefix is a multiple of 8
                            if (eth_stack["gateway_prefix"] % 8
                                    is not 0) or (eth_stack["gateway_prefix"] /
                                                  8 > 4):
                                raise ValueError(
                                    "Gateway prefix must be either 8, 16, 24, or 32"
                                )

                            num_octets = eth_stack["gateway_prefix"] / 8
                            gateway = ".".join(
                                eth_stack["ip"].split(".")[:num_octets])
                            ipv4.GatewayIp.Single(value=gateway)
                            ipv4.ResolveGateway.Single(False)
                            ix_endpoints[f"{name}.{protocol_stack}.ip"] = ipv4

                        ix_endpoints[f"{name}.{protocol_stack}"] = ix_eth

        ix_network.info('Create Traffic Items')
        trafficItem = []
        for i, traffic_item in self._traffic_items["traffic_items"]:
            print(
                f'\rCreating Traffic Item {i} of {len(self._traffic_items["traffic_items"])}...',
                end="")
            # Create a traffic item.  This scenario, all traffic is uni-directional.
            # Need to specify the type so that the appropriate packet headers are applied.
            trafficItem.append(
                ix_network.Traffic.TrafficItem.add(
                    Name=f'Traffic Item {i}',
                    BiDirectional=False,
                    TrafficType=traffic_item["type"]))

            # Add the source and destination.  Note that a variety of types are supported here -
            # you can specify a topology, or a stack like ethernet or IPv4.

            # If you specify something that has multiple stacks, then you get the frames split
            # between them which is typically not what we want.

            # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide
            # the specific IPv4 stack you want to use.
            for j in range(0, len(traffic_item["src"])):
                trafficItem[i].EndpointSet.add(
                    Sources=ix_endpoints[traffic_item["src"][j]],
                    Destinations=ix_endpoints[traffic_item["dst"][j]])
                configElement = trafficItem[i].ConfigElement.find()[0]

            # If this traffic item is UDP, add the UDP packet header with appropriate destination port.
            # Our scenario doesn't care about the source port.
            if (traffic_item["udp"] == True):
                udpFieldObj = self._create_packet_header(
                    trafficItem[i],
                    packetHeaderToAdd='UDP',
                    appendToStack='IPv4')
                udpDstField = udpFieldObj.find(DisplayName='UDP-Dest-Port')
                udpDstField.Auto = False
                udpDstField.SingleValue = traffic_item["dst_port"]

            # Configure for a particular bit rate.  By fixing frame size at 128 bytes, Keysight will determine
            # the correct frame rate to use to achieve the specified bit rate.
            configElement.FrameRate.update(Type='bitsPerSecond',
                                           BitRateUnitsType='kbitsPerSec',
                                           Rate=traffic_item["tx_rate"])
            configElement.FrameSize.FixedSize = 128

            # This adds Traffic Item to the Statistics Tracking field.
            # Without this, keysight will not track frame drops, latencies, etc.
            for j in range(0, len(traffic_item["src"])):
                trafficItem[i].Tracking.find()[j].TrackBy = [
                    f'trackingenabled{j}'
                ]

            # This generates the frames based on the previous configuration.
            trafficItem[i].Generate()

        # Not clear why the following steps don't work, but not all the traffic starts.
        # ix_network.Traffic.Apply()
        # ix_network.StartAllProtocols(Arg1='sync')
        # ix_network.Traffic.Start()

        # This does work, and was discovered using firefox inspector, as what the Web UI is doing when the Green Test Start button is pressed.
        # arg2 = True means to forcefully grab the ports
        # Note that this is non-blocking, but any further operation that relies on the traffic will block until the traffic is started

    def run_session(self, session_name, api_server_ip, log_level):

        # LogLevel: none, info, warning, request, request_response, all
        # all can be useful for debugging issues but is very verbose
        ix_network = TestPlatform(api_server_ip).Sessions.find(
            Name=session_name, Id=None)
        ix_network.SetLoggingLevel(log_level)

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
            statsView = ix_network.Statistics.View.find(
                Caption='Flow Statistics')
            RxRates = statsView.GetColumnValues(Arg2='Rx Rate (Kbps)')
            print(RxRates)
            time.sleep(1)

        # TODO: Invoke script to test the scenario

        if self._dry_run == False:
            ix_network.Globals.Testworkflow.Stop()

        if debugMode == False:
            for vport in ix_network.Vport.find():
                vport.ReleasePort()

        # For linux and connection_manager only
        if session.TestPlatform.Platform != 'windows':
            session.Session.remove()
