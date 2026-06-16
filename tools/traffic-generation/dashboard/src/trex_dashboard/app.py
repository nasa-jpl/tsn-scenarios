"""Flask dashboard application."""

import argparse
import logging
import os

from flask import Flask, jsonify, send_file

from .config import load_config
from .trex_source import TrexSource
from .hardware_source import HardwareSource

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app(cfg, trex_src: TrexSource, hw_src: HardwareSource | None):
    app = Flask(__name__)

    use_trex_latency = cfg.latency_source == "trex" and cfg.latency_sink == "trex"
    use_hw_latency = hw_src is not None

    @app.route("/")
    def index():
        return send_file(os.path.join(STATIC_DIR, "dashboard.html"))

    @app.route("/api/config")
    def api_config():
        return jsonify({
            "latency_source": cfg.latency_source,
            "latency_sink": cfg.latency_sink,
            "has_trex_latency": use_trex_latency,
            "has_hw_latency": use_hw_latency,
            "streams": [
                {"pg_id": s.pg_id, "name": s.name, "color": s.color}
                for s in cfg.streams
            ],
        })

    @app.route("/api/stats")
    def api_stats():
        try:
            data = trex_src.get_stats()
        except Exception as e:
            return jsonify({"error": str(e)}), 503

        if not use_trex_latency:
            for pg_id, stream in data["streams"].items():
                stream.pop("trex_lat_avg_us", None)
                stream.pop("trex_lat_min_us", None)
                stream.pop("trex_lat_max_us", None)
                stream.pop("trex_jitter_us", None)

        if use_hw_latency:
            hw_stats = hw_src.get_latency_stats()
            for pg_id, stream in data["streams"].items():
                ts = hw_stats.get(pg_id, {})
                stream["tap_lat_avg_us"] = ts.get("avg_us", 0)
                stream["tap_lat_min_us"] = ts.get("min_us", 0)
                stream["tap_lat_max_us"] = ts.get("max_us", 0)
                stream["tap_sample_count"] = ts.get("count", 0)
                stream["tap_pkt_count"] = ts.get("pkt_count", 0)

        data["has_trex_latency"] = use_trex_latency
        data["has_hw_latency"] = use_hw_latency
        return jsonify(data)

    return app


def main():
    parser = argparse.ArgumentParser(description="T-Rex Dashboard")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    parser.add_argument("--port", type=int, default=5000, help="Dashboard HTTP port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    log.info("Config loaded: source=%s, sink=%s, streams=%s",
             cfg.latency_source, cfg.latency_sink, [s.pg_id for s in cfg.streams])

    trex_src = TrexSource(cfg)

    hw_src = None
    if cfg.latency_source != "trex" or cfg.latency_sink != "trex":
        hw_src = HardwareSource(cfg)
        hw_src.start()

    app = create_app(cfg, trex_src, hw_src)
    app.run(host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
