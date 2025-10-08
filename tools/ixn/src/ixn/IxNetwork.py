import os
import time
from .IxValidate import IxValidate
from ixnetwork_restpy import PortMapAssistant, SessionAssistant, TestPlatform


class IxNetworkError(Exception):
    def __init__(self, message):
        super().__init__(message)


class IxNetwork:
    # Set up logging level dict
    LOG_LEVELS = {
        "none": SessionAssistant.LOGLEVEL_NONE,
        "info": SessionAssistant.LOGLEVEL_INFO,
        "warning": SessionAssistant.LOGLEVEL_WARNING,
        "request": SessionAssistant.LOGLEVEL_REQUEST,
        "request_response": SessionAssistant.LOGLEVEL_REQUEST_RESPONSE,
        "all": SessionAssistant.LOGLEVEL_ALL,
    }

    def __init__(
        self,
        api_server_ip,
        chassis_ip,
        chassis_slot_number,
        session_name,
        verbosity=None,
        log_file=None,
    ):
        self._username = os.getenv("IXN_USER")
        self._password = os.getenv("IXN_PASS")

        # Our API server and chassis are same device
        self._api_server_ip = api_server_ip
        self._chassis_ip = chassis_ip

        self._session_name = session_name

        # Some Keysight products have multiple slots within a single chassis, we just have 1 slot
        self._chassis_slot_number = chassis_slot_number

        # How verbose do we want the output
        if verbosity is None:
            self._verbosity = self.LOG_LEVELS["none"]
        else:
            self._verbosity = self.LOG_LEVELS[verbosity]

        self._log_file = log_file
        if self._log_file is None:
            self._log_file = (
                f"{self._session_name}_{time.strftime('%Y%m%d-%H%M%S')}.log"
            )

        self._ix_session = None
        self._ix_network = None

    def _create_packet_header(
        self, trafficItemObj, packetHeaderToAdd=None, appendToStack=None
    ):
        """This function is used to create packet headers that can then be manipulated by the caller"""

        configElement = trafficItemObj.ConfigElement.find()

        # Do the followings to add packet headers on the new traffic item

        # Get a list of all the available protocol templates to create (packet headers)
        availableProtocolTemplates = []
        for protocolHeader in self._ix_network.Traffic.ProtocolTemplate.find():
            availableProtocolTemplates.append(protocolHeader.DisplayName)

        packetHeaderProtocolTemplate = self._ix_network.Traffic.ProtocolTemplate.find(
            DisplayName="^{}".format(packetHeaderToAdd)
        )
        if len(packetHeaderProtocolTemplate) == 0:
            self._ix_network.info(
                "{} protocol template not supported, skipping. Supported procotol templates: {}".format(
                    packetHeaderToAdd, "|".join(availableProtocolTemplates)
                )
            )
            return None

        # 2> Append the <new packet header> object after the specified packet header stack.
        appendToStackObj = configElement.Stack.find(
            DisplayName="^{}".format(appendToStack)
        )
        self._ix_network.info(
            "Adding protocolTemplate: {} on top of stack: {}".format(
                packetHeaderProtocolTemplate.DisplayName, appendToStackObj.DisplayName
            )
        )

        # if self._debug_mode is True:
        #     self._ix_network.info(format(packetHeaderProtocolTemplate))
        #     self._ix_network.info(format(appendToStackObj))
        appendToStackObj.Append(Arg2=packetHeaderProtocolTemplate)

        # 3> Get the new packet header stack to use it for appending an IPv4 stack after it.
        # Look for the packet header object and stack ID.
        packetHeaderStackObj = configElement.Stack.find(
            DisplayName="^{}".format(packetHeaderToAdd)
        )

        # 4> In order to modify the fields, get the field object
        packetHeaderFieldObj = packetHeaderStackObj.Field.find()

        return packetHeaderFieldObj

    def _validate_traffic_endpoint(self, traffic_endpoint):
        """Takes in an endpoint of the form <EP>.<DG>.<protocol_stack>
        and makes sure that the corresponding endpoint is in the topology"""
        keys = traffic_endpoint.split(".")

        # Check endpoint name and device_group
        endpoints = self._endpoints["endpoints"]
        if not endpoints.get(keys[0], False):
            raise IxNetworkError(f"{keys[0]} not a valid endpoint in toplogy")

        if not endpoints[keys[0]].get("device_groups", False):
            raise IxNetworkError(
                f"{keys[0]} does not contain a device_groups in toplogy"
            )

        # Check if we are using the whole endpoint and not jus one interface
        if len(keys) == 1:
            # We are good as the traffic endpoint was already found
            return

        eps = endpoints[keys[0]]["device_groups"]
        for key in keys[1:]:
            if key not in eps:
                raise RuntimeError(f"{traffic_endpoint} not a valid endpoint")
            eps = eps[key]

    def _validate_configs(self):
        """Takes in the endpoints and traffic_items read from the yaml files and validates them"""

        # Make sure each src and dst lists match in size, and have a corresponding endpoint
        for traffic_item in self._traffic_items["traffic_items"]:
            if not isinstance(traffic_item["src"], list):
                raise RuntimeError(
                    f"Traffic source {traffic_item['src']} must be a list"
                )

            if not isinstance(traffic_item["dst"], list):
                raise RuntimeError(
                    f"Traffic source {traffic_item['dst']} must be a list"
                )

            if len(traffic_item["src"]) != len(traffic_item["dst"]):
                raise RuntimeError("Traffic src and dst list sizes must match")

            for traffic_endpoint in traffic_item["src"]:
                self._validate_traffic_endpoint(traffic_endpoint)

            for traffic_endpoint in traffic_item["dst"]:
                self._validate_traffic_endpoint(traffic_endpoint)

    def _get_session_by_name(self):
        """Checks to see if the session name exists on the server"""
        platform = TestPlatform(self._api_server_ip)
        platform.Authenticate(self._username, self._password)

        session = platform.Sessions.find(Name=self._session_name, Id=None)

        if session.index == -1:
            raise IxNetworkError(
                f"Unable to find session with name {self._session_name}"
            )

        print(f"Found session {self._session_name}")

        return session

    def create_session(
        self, endpoints, traffic_items, dry_run=False, force_port_ownership=True
    ):
        """Creates a session with ixnetwork_restpy"""

        print("Starting session...")
        self._ix_session = SessionAssistant(
            IpAddress=self._api_server_ip,
            RestPort=None,
            UserName=self._username,
            Password=self._password,
            SessionName=self._session_name,
            SessionId=None,
            ApiKey=None,
            ClearConfig=True,
            LogLevel=self._verbosity,
            LogFilename=self._log_file,
        )

        self._ix_network = self._ix_session.Ixnetwork

        self._endpoints = endpoints
        self._traffic_items = traffic_items

        self._validate_configs()

        # LogLevel: none, info, warning, request, request_response, all
        # all can be useful for debugging issues but is very verbose

        print("Assigning Ports...")
        self._ix_network.info("Assign ports")
        portMap = self._ix_session.PortMapAssistant()
        # Each port consists of the IP address of the chassis, the card #, and the port #
        vport = dict()
        for key, endpoint in self._endpoints["endpoints"].items():
            portName = f"Port_{key}"
            vport[key] = portMap.Map(
                IpAddress=self._chassis_ip,
                CardId=self._chassis_slot_number,
                PortId=endpoint["port_num"],
                Name=portName,
            )

        if dry_run is False:
            print("Connecting Ports...")
            portMap.Connect(force_port_ownership)

        # Setup endpoints
        topologies = dict()
        ix_endpoints = dict()
        for name, endpoint in self._endpoints["endpoints"].items():
            print(f"Creating {name} topology...")

            if "device_groups" in endpoint:
                topologies[name] = self._ix_network.Topology.add(
                    Name=name, Ports=vport[name]
                )
                ix_endpoints[name] = topologies[name]
                ix_group = topologies[name].DeviceGroup.add(
                    Name=f"{name}.DG", Multiplier="1"
                )

                # Go through all protocol stacks in this endpoint
                device_groups = endpoint["device_groups"]
                for j, protocol_stack in enumerate(device_groups, start=1):
                    self._ix_network.info(f"Creating {name}.{protocol_stack}")
                    if protocol_stack.startswith("eth"):
                        eth_stack = device_groups[protocol_stack]
                        ix_eth = ix_group.Ethernet.add(Name=f"{name}.{protocol_stack}")
                        ix_eth.Mac.Single(value=eth_stack["mac"])

                        if "vlan" in eth_stack:
                            ix_eth.EnableVlans.Single(True)
                            ix_eth_vlan = ix_eth.Vlan.find()[0].VlanId.SingleValue(
                                eth_stack["vlan"]
                            )

                        if eth_stack["ipv4"] is True:
                            self._ix_network.info(f"Configuring {name} IP{j}")
                            ipv4 = ix_eth.Ipv4.add(Name=f"{name}.{protocol_stack}.ip")
                            ipv4.Address.Single(value=eth_stack["ip"])
                            ipv4.Prefix.Single(value=str(eth_stack["gateway_prefix"]))

                            ipv4.GatewayIp.Single(value=eth_stack["gateway"])
                            ipv4.ResolveGateway.Single(False)
                            ix_endpoints[f"{name}.{protocol_stack}.ip"] = ipv4

                        ix_endpoints[f"{name}.{protocol_stack}"] = ix_eth

        self._ix_network.info("Create Traffic Items")
        trafficItem = []
        for i, traffic_item in enumerate(self._traffic_items["traffic_items"]):
            print(
                f"Creating Traffic Item {i + 1} of {len(self._traffic_items['traffic_items'])}..."
            )
            # Create a traffic item.  This scenario, all traffic is uni-directional.
            # Need to specify the type so that the appropriate packet headers are applied.
            trafficItem.append(
                self._ix_network.Traffic.TrafficItem.add(
                    Name=f"Traffic Item {i + 1}",
                    BiDirectional=False,
                    TrafficType=traffic_item["type"],
                )
            )

            # Add the source and destination.  Note that a variety of types are supported here -
            # you can specify a topology, or a stack like ethernet or IPv4.

            # If you specify something that has multiple stacks, then you get the frames split
            # between them which is typically not what we want.

            # So for example if a topology ep3_topology has 2 IPv4 stacks, you need to provide
            # the specific IPv4 stack you want to use.
            for src, dst in zip(traffic_item["src"], traffic_item["dst"]):
                trafficItem[i].EndpointSet.add(
                    Sources=ix_endpoints[src], Destinations=ix_endpoints[dst]
                )
                configElement = trafficItem[i].ConfigElement.find()[0]

            # If this traffic item is UDP, add the UDP packet header with appropriate destination port.
            # Our scenario doesn't care about the source port.
            if traffic_item["udp"]:
                udpFieldObj = self._create_packet_header(
                    trafficItem[i], packetHeaderToAdd="UDP", appendToStack="IPv4"
                )
                udpDstField = udpFieldObj.find(DisplayName="UDP-Dest-Port")
                udpDstField.Auto = False
                udpDstField.SingleValue = traffic_item["dst_port"]

            # Configure for a particular bit rate.  By fixing frame size at 128 bytes, Keysight will determine
            # the correct frame rate to use to achieve the specified bit rate.
            configElement.FrameRate.update(
                Type="bitsPerSecond",
                BitRateUnitsType="kbitsPerSec",
                Rate=traffic_item["tx_rate"],
            )
            configElement.FrameSize.FixedSize = 128

            # This adds Traffic Item to the Statistics Tracking field.
            # Without this, keysight will not track frame drops, latencies, etc.
            for j in range(0, len(traffic_item["src"])):
                trafficItem[i].Tracking.find()[j].TrackBy = [f"trackingenabled{j}"]

            # This generates the frames based on the previous configuration.
            trafficItem[i].Generate()

    def run_session(self, run_time_sec, dry_run=False, validation_func=None):
        """Run an existing session"""

        self._ix_session = self._get_session_by_name()
        self._ix_network = self._ix_session.Ixnetwork

        if dry_run is False:
            print("Starting traffic...")
            self._ix_network.Globals.Testworkflow.Start(arg2=True)

            # Wait until traffic is running
            print("Waiting for traffic to start", end="")
            while not self._ix_network.Traffic.IsTrafficRunning:
                print(".", end="")
                time.sleep(0.5)
            print()

            # Wait additional time because if we grab traffic stats instantly,
            # the switch won't have had an opportunity to do the flow metering,
            # and it can take a little while for the keysight stats
            # "moving average" to not reflect the startup transient

            # TODO: Using this code snippet, sometimes the rates are settled by
            # 2 seconds, usually 3, sometimes more
            # Leaving this in for debugging purposes.
            # One possibility is to make a scenario-specific check, like wait
            # until some rate is within tolerance of the expected value, but
            # that might just get stuck waiting if the switch or keysight are
            # not configured correctly. Another method could be to calculate
            # the rate of change of every stats item of interest and wait until
            # some convergence across the majority of them.

            if run_time_sec != 0:
                print("Waiting for statistics to settle...")
                # wait for a specified amount of time before getting statistics
                time.sleep(run_time_sec)

                self.validate_session(validation_func)

                self._ix_network.Globals.Testworkflow.Stop()

                for vport in self._ix_network.Vport.find():
                    vport.ReleasePort()

    def validate_session(self, validation_func):
        if validation_func is None:
            raise IxNetworkError("Must define a validation function")

        if self._ix_network is None:
            self._ix_session = self._get_session_by_name()
            self._ix_network = self._ix_session.Ixnetwork

        ix_validate = IxValidate(self._ix_network)

        if hasattr(ix_validate, validation_func):
            callable_validation_func = getattr(ix_validate, validation_func)
            if callable(callable_validation_func):
                callable_validation_func()
            else:
                raise IxNetworkError(
                    f"Validation function IxValidate.{validation_func} must be callable"
                )
        else:
            raise IxNetworkError(
                f"Validation function IxValidate.{validation_func} does not exist"
            )

    def stop_session(self, dry_run):
        """Stop an existing session"""

        self._ix_session = self._get_session_by_name()
        self._ix_network = self._ix_session.Ixnetwork

        if dry_run is False:
            print("Stopping traffic...")
            self._ix_network.Globals.Testworkflow.Stop()

            for vport in self._ix_network.Vport.find():
                vport.ReleasePort()
