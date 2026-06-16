"""Load dashboard configuration from TOML."""

import dataclasses
import tomllib
from pathlib import Path

VALID_ENDPOINTS = ("trex", "nic", "tap")


@dataclasses.dataclass
class StreamDef:
    pg_id: int
    name: str
    color: str
    udp_port: int | None = None


@dataclasses.dataclass
class Config:
    trex_server: str
    trex_api_path: str
    latency_source: str  # "trex" | "nic" | "tap"
    latency_sink: str    # "trex" | "nic" | "tap"
    nic_ingress_interface: str | None
    nic_egress_interface: str | None
    tap_ingress_interface: str | None
    tap_egress_interface: str | None
    streams: list[StreamDef]
    dashboard_port: int = 5000


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    trex = raw.get("trex", {})
    latency = raw.get("latency", {})
    nic = raw.get("nic", {})
    tap = raw.get("tap", {})

    streams = [
        StreamDef(
            pg_id=s["pg_id"],
            name=s["name"],
            color=s["color"],
            udp_port=s.get("udp_port"),
        )
        for s in raw.get("streams", [])
    ]

    source = latency.get("source", "trex")
    sink = latency.get("sink", "trex")

    if source not in VALID_ENDPOINTS:
        raise ValueError(f"latency.source must be one of {VALID_ENDPOINTS}, got '{source}'")
    if sink not in VALID_ENDPOINTS:
        raise ValueError(f"latency.sink must be one of {VALID_ENDPOINTS}, got '{sink}'")

    return Config(
        trex_server=trex.get("server", "127.0.0.1"),
        trex_api_path=trex.get("api_path", ""),
        latency_source=source,
        latency_sink=sink,
        nic_ingress_interface=nic.get("ingress_interface"),
        nic_egress_interface=nic.get("egress_interface"),
        tap_ingress_interface=tap.get("ingress_interface"),
        tap_egress_interface=tap.get("egress_interface"),
        streams=streams,
    )
