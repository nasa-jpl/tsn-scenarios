# TAS T-Rex Scenario

## Prerequisites
- T-Rex installed on ngasrv0
    - Shared installation at `/opt/trex/v3.08`
- `tsn-scenarios` repo cloned (for the `istax` CLI tool)

## 1. Upload switch config

```
cd tsn-scenarios/tools/istax
uv run istax upload ngatsnsw2 ../../../traffic-generation/tas/switch.cfg
```

## 2. Start T-Rex server

Terminal 1:
```
cd /opt/trex/v3.08
sudo ./t-rex-64 -i --cfg <PATH to traffic-generation repo>/tas/trex_cfg.yaml
```

## 3. Start traffic

Terminal 2:
```
cd /opt/trex/v3.08
./trex-console
```

In the trex console (only need to do this once):
```
service -p 0
service -p 1
l2 -p 0 --dst 02:00:00:00:00:03
l2 -p 1 --dst 02:00:00:00:00:03
service -p 0 --off
service -p 1 --off
portattr -p 0 --prom on
```

Start traffic (in trex console):
```
start -f /home/ndhamani/traffic-generation/tas/tsn_profile_tas.py -p 1 --force
```

Higher rate (this might hang due to hitting cpu limits):
```
start -f /home/ndhamani/traffic-generation/tas/tsn_profile_tas.py -p 1 --force -t pps=500000,bg_pps=25000
```

Stats: `tui` (q to exit)

Stop traffic: `stop -p 1`

## 4. Start the dashboard

Terminal 3 (on ngasrv0):
```
cd traffic-generation/dashboard
uv run trex-dashboard --config config.toml
```

Opens on `http://ngasrv0:5000`. Change the port with `--port`.

If connecting from Windows, you can `ssh -L 5000:localhost:5000 user@host` and then from a browser on the windows machine go to `http://localhost:5000`.

The `[latency]` section in `config.toml` controls where timestamps come from:
- `source = "trex"` / `sink = "trex"` — software latency only, no extra processes
- `source = "tap"` / `sink = "tap"` — ProfiShark taps (must be plugged in and synced, see [network-tap.md](network-tap.md))
- `source = "nic"` / `sink = "nic"` — NIC HW timestamps via tcpdump + phc2sys

See [dashboard.md](dashboard.md) for architecture details and standalone usage.
