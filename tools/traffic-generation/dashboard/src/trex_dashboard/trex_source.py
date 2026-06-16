"""T-Rex STLClient stats collector."""

import logging
import sys
import threading

from .config import Config

log = logging.getLogger(__name__)


class TrexSource:
    def __init__(self, config: Config):
        self._cfg = config
        self._client = None
        self._lock = threading.Lock()
        self._debugged = False

        if config.trex_api_path and config.trex_api_path not in sys.path:
            sys.path.insert(0, config.trex_api_path)

    def _connect(self):
        from trex.stl.api import STLClient

        if self._client is not None:
            if self._client.is_connected():
                return self._client
            try:
                self._client.disconnect()
            except Exception:
                pass

        self._client = STLClient(server=self._cfg.trex_server)
        self._client.connect()
        return self._client

    def get_stats(self) -> dict:
        with self._lock:
            try:
                return self._collect()
            except Exception as e:
                log.warning("T-Rex stats error: %s", e)
                self._client = None
                raise

    def _collect(self) -> dict:
        c = self._connect()
        pg_ids = [s.pg_id for s in self._cfg.streams]

        stats = c.get_stats(ports=[0, 1])
        pgid_stats = c.get_pgid_stats(pgid_list=pg_ids)

        if not self._debugged:
            self._debugged = True
            g_keys = list(stats.get("global", {}).keys())
            log.info("T-Rex global keys: %s", g_keys)
            for pg_id in pg_ids:
                lat_entry = pgid_stats.get("latency", {}).get(pg_id, {})
                log.info("pg_id %s latency entry: %s", pg_id, lat_entry)

        streams = {}
        flow_stats = pgid_stats.get("flow_stats", {})
        latency_stats = pgid_stats.get("latency", {})

        for s in self._cfg.streams:
            pg = flow_stats.get(s.pg_id, {})
            lat = latency_stats.get(s.pg_id, {}).get("latency", {})

            streams[s.pg_id] = {
                "name": s.name,
                "color": s.color,
                "pg_id": s.pg_id,
                "trex_lat_avg_us": lat.get("average", 0),
                "trex_lat_min_us": lat.get("total_min", 0),
                "trex_lat_max_us": lat.get("total_max", 0),
                "trex_jitter_us": lat.get("jitter", 0),
            }

        g = stats.get("global", {})

        cpu_per_core = []
        for key in sorted(g.keys()):
            if key.startswith("cpu_util_") and key != "cpu_util":
                val = g[key]
                if isinstance(val, (int, float)):
                    cpu_per_core.append(val)
                elif isinstance(val, list):
                    cpu_per_core.extend(val)

        return {
            "streams": streams,
            "global": {
                "cpu_util": g.get("cpu_util", 0),
                "cpu_util_per_core": cpu_per_core,
                "tx_bps": g.get("tx_bps", 0),
                "rx_bps": g.get("rx_bps", 0),
                "tx_pps": g.get("tx_pps", 0),
                "rx_pps": g.get("rx_pps", 0),
            },
        }
