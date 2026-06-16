# DPDK Investigation

## Current State
T-Rex v3.08 on ngasrv0 uses **AF_PACKET PMD**, not native DPDK. Using the trex provided `dpdk_setup_ports.py` script, we can see we have DPDK compatible NICs:

```
Network devices using DPDK-compatible driver
============================================
0000:03:00.0 '82599ES 10-Gigabit SFI/SFP+ Network Connection' drv=igb_uio unused=
0000:03:00.1 '82599ES 10-Gigabit SFI/SFP+ Network Connection' drv=igb_uio unused=
0000:13:00.0 '82599ES 10-Gigabit SFI/SFP+ Network Connection' drv=igb_uio unused=
0000:13:00.1 '82599ES 10-Gigabit SFI/SFP+ Network Connection' drv=igb_uio unused=

Network devices using kernel driver
===================================
0000:02:00.0 '82545EM Gigabit Ethernet Controller (Copper)' if=eth2 drv=e1000 unused=igb_uio *Active*

Other network devices
=====================
```

However, if we were actually using native dpdk, we wouldn't be able to run `tcpdump` on that NIC since it would be bound to DPDK (kernel wont have access). However, we see that is not the case. Additionally when checking port attributes in trex, we see the driver is net_af_packet. 

```
trex>portattr
Port Status

     port       |          0           |          1           
----------------+----------------------+---------------------
driver          |    net_af_packet     |    net_af_packet     
description     |       Unknown        |       Unknown        
link status     |          UP          |          UP          
link speed      |       10 Gb/s        |       10 Gb/s        
port status     |         IDLE         |         IDLE         
promiscuous     |         off          |         off          
multicast       |         off          |         off          
flow ctrl       |         N/A          |         N/A          
vxlan fs        |          -           |          -           
--              |                      |                      
layer mode      |         IPv4         |         IPv4         
src IPv4        |       10.0.0.2       |       10.0.1.1       
IPv6            |         off          |         off          
src MAC         |  24:5e:be:88:af:37   |  24:5e:be:88:af:36   
---             |                      |                      
Destination     |       10.0.1.1       |       10.0.0.2       
ARP Resolution  |      unresolved      |      unresolved      
----            |                      |                      
VLAN            |          -           |          -           
-----           |                      |                      
PCI Address     |         N/A          |         N/A          
NUMA Node       |          -1          |          -1          
RX Filter Mode  |    hardware match    |    hardware match    
RX Queueing     |         off          |         off          
Grat ARP        |         off          |         off          
------
```


Running with AF_PACKET means that DPDK falls back to kernel sockets: The AF_PACKET socket in Linux allows an application to receive and send raw packets. This Linux-specific PMD binds to an AF_PACKET socket and allows a DPDK application to send and receive raw packets through the Kernel.

## Why Not Native DPDK

**No VFIO kernel module**

Native DPDK needs `vfio-pci` to unbind NICs from kernel and expose hardware to userspace. Kernel `6.12.29-upstream` was compiled with `CONFIG_VFIO` disabled:
```
$ grep VFIO /boot/config-$(uname -r)
# CONFIG_VFIO is not set
```