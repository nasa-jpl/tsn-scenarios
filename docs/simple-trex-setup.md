# TREX Trafic Generation

Simple setup to get trex traffic generation in loopback mode running on either `hpscupn2` or local (tested only on M-series macbook). Since we don't have access to another NIC for now, we create 2 virtual ports within a docker network to simulate. This also enables the `low_end` option in the configuration.

## Docker Setup

1. Create dir `trex-docker` and the following 3 files under: `Dockerfile`, `entrypoint.sh`, `trex_cfg_cat9k.yaml`. See below for contents of these files
2. From within the `trex-docker` directory, build the image: `docker build . -t trex:latest`
3. Run the docker container: `docker run --rm -it --privileged --cap-add=ALL trex:latest`
4. This should bring you into a shell within the container. Start trex service: `./t-rex-64 -i --cfg /etc/trex_cfg_cat9k.yaml`
5. From a new terminal, run `docker ps`, grab the `CONTAINER ID` of the trex docker container
6. Spawn a new shell with the container specified: `docker exec -it <CONTAINER_ID> bash`
7. Launch TREX console: `./trex-console`
8. Start traffic generation: `start -f stl/imix.py -m 10kpps --port 0`
    - Modify kpps as desired
9. Launch stats output: `tui`
10. To stop traffic generation, exit `tui` console, and enter `stop` in trex-console


### Dockerfile contents
```
FROM ubuntu:22.04
RUN apt-get update
RUN apt-get -y install python3 \
             wget \
             bash \
             net-tools \
             netbase \
             strace \
             iproute2 \
             iputils-ping \
             pciutils \
             vim
RUN wget --no-check-certificate --no-cache https://trex-tgn.cisco.com/trex/release/latest && \
    tar -zxvf latest -C / && \
    chown root:root /v3.08
COPY trex_cfg_cat9k.yaml /etc/trex_cfg_cat9k.yaml
WORKDIR /v3.08

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD []
```

NOTE: if running on arm based device such as M-series mac, specify the platform in the first line of the docker file as such: 
```
FROM --platform=linux/amd64 ubuntu:22.04
```

### entrypoint.sh contents
```
#!/usr/bin/env bash
set -euo pipefail

# create veth loopback pair if it doesn't exist
if ! ip link show veth0 >/dev/null 2>&1; then
  ip link add veth0 type veth peer name veth1
  ip link set veth0 up
  ip link set veth1 up
fi


exec /bin/bash -l
#exec /v3.08/t-rex-64 -i --cfg /etc/trex_cfg_cat9k.yaml
```

### trex_cfg_cat9k.yaml contents
```
- port_limit    : 2
  version       : 2
  low_end       : true
  interfaces    : ["veth0", "veth1"]
  port_info     :  # set eh mac addr
                 - ip         : 10.0.0.2
                   default_gw : 10.0.1.1
                 - ip         : 10.0.1.1
                   default_gw : 10.0.0.2
```