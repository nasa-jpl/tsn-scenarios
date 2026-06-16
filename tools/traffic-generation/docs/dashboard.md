# Dashboard

## What It Does

Connects to a running TRex instance, polls stats, and serves a web UI showing bandwidth, CPU, and per-stream latency. Optionally runs hardware capture backends (NIC or ProfiShark taps) for ns-precision latency measurement.

## Architecture

Two standalone modules do the actual work:

- **`trex_source.py`** — Connects to TRex via the STL API. Polls per-stream TX/RX counters and software latency stats. Reconnects automatically if TRex restarts.
- **`hardware_source.py`** — Runs capture processes (tcpdump or tshark) and matches ingress/egress packets to compute hardware-timestamped latency. Supports NIC HW timestamps (phc2sys synced) and ProfiShark taps (GPS synced).

Both are plain Python classes (`TrexSource` and `HardwareSource`) that can be imported independently — they don't depend on Flask or the dashboard UI. The intent is for these to be reusable in unit tests, automation scripts, or wrappers around other tools (e.g., Keysight).

`app.py` is just the glue: loads config, instantiates the sources, and serves a Flask API that the frontend polls.

## Config

Everything is in `config.toml`. Key sections:

```toml
[trex]
server = "127.0.0.1"
api_path = "/opt/trex/v3.08/automation/trex_control_plane/interactive"

[latency]
# where ingress (TX) and egress (RX) timestamps come from
# options: "trex" | "nic" | "tap"
source = "tap"
sink = "tap"

[nic]
ingress_interface = "enp4s0"
egress_interface = "enp3s0"

[tap]
ingress_interface = "Profishark44b7d0e809c6"
egress_interface = "Profishark44b7d0e7ecc7"

[[streams]]
pg_id = 2
name = "Queue 2 (PCP 2)"
color = "#fb8c00"
udp_port = 5002
```

- `latency.source` / `latency.sink` control which backend provides timestamps. Set both to `"trex"` for software-only (no capture processes started).
- `streams` must match the `pg_id` values in your TRex traffic profile. The `udp_port` field is used by the tap parser to identify which stream a packet belongs to when there's no STLFlowLatencyStats trailer.

## Using the Modules Standalone

```python
from trex_dashboard.config import load_config
from trex_dashboard.trex_source import TrexSource
from trex_dashboard.hardware_source import HardwareSource

cfg = load_config("config.toml")

# TRex software stats
trex = TrexSource(cfg)
stats = trex.get_stats()
# stats["streams"][pg_id]["trex_lat_avg_us"], etc.

# Hardware latency (tap or NIC)
hw = HardwareSource(cfg)
hw.start()
# ... let it capture for a while ...
latency = hw.get_latency_stats()
# latency[pg_id]["avg_us"], ["min_us"], ["max_us"], ["count"]
hw.stop()
```

`HardwareSource.start()` spawns background threads for capture and cleanup. Call `stop()` to shut them down.

## Packet Matching

The tap/NIC backends need to match the same packet seen on the ingress tap to the same packet on the egress tap. Two strategies:

1. **STLFlowLatencyStats trailer** — TRex embeds a 16-byte trailer with a sequence number. Parser reads magic byte `0xAB` at end of payload. Works for continuous streams.
2. **Field engine packet ID** — For burst streams (where STLFlowLatencyStats can't be used), the traffic profile injects a random 64-bit ID at the start of the UDP payload. Parser reads the first 8 bytes.

The parser tries the trailer first, then falls back to the field engine ID. Both continuous and burst streams can run simultaneously.

Matching is bidirectional: whichever side (ingress or egress) sees a packet first stores it in a map keyed by the packet ID. When the other side sees the same ID, it computes latency and removes the entry. This handles tshark delivery ordering differences between the two capture processes.

Unmatched entries expire after 10 seconds.
