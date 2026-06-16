"""Hardware latency source — configurable ingress/egress capture backends.

Supports any combination of:
  - nic: tcpdump with NIC HW timestamps (phc2sys synced)
  - tap: tshark on ProfiShark extcap interface (separate ingress/egress taps)

Packets matched by (hw_id, seq) from the T-Rex flow stats trailer.
Latency = egress_ts - ingress_ts (tap timesources are synced, raw delta is used).
"""

import collections
import logging
import os
import struct
import subprocess
import threading
import time

from .config import Config

log = logging.getLogger(__name__)

TRAILER_MAGIC_BYTE = 0xab
TRAILER_SIZE = 16
PCAP_GLOBAL_HDR_SIZE = 24
PCAP_PKT_HDR_SIZE = 16
INGRESS_TTL = 10.0

# pcapng block types
PCAPNG_SHB = 0x0A0D0D0A   # Section Header Block
PCAPNG_IDB = 0x00000001   # Interface Description Block
PCAPNG_EPB = 0x00000006   # Enhanced Packet Block
PCAPNG_BLOCK_HDR_SIZE = 8  # type(4) + length(4)


def parse_trailer(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < TRAILER_SIZE:
        return None
    trailer = payload[-TRAILER_SIZE:]
    magic, hw_id, seq, _ = struct.unpack("<HHIq", trailer)
    if (magic & 0xFF) != TRAILER_MAGIC_BYTE:
        return None
    return (hw_id, seq)


def parse_packet(pkt_data: bytes) -> tuple[int, int | None, int | None] | None:
    """Parse a UDP packet, returning (dstport, hw_id, seq).

    Tries two matching strategies:
      1. STLFlowLatencyStats trailer (magic 0xAB at end of payload)
      2. Field-engine seq number (first 4 bytes of UDP payload)
    Falls back to (dstport, None, None) if neither is found.
    """
    if len(pkt_data) < 34:
        return None
    ethertype = struct.unpack("!H", pkt_data[12:14])[0]
    ip_offset = 18 if ethertype == 0x8100 else 14
    udp_offset = ip_offset + 20
    if len(pkt_data) < udp_offset + 8:
        return None
    dstport = struct.unpack("!H", pkt_data[udp_offset + 2:udp_offset + 4])[0]
    payload_offset = udp_offset + 8
    udp_payload = pkt_data[payload_offset:]
    # Try STLFlowLatencyStats trailer first
    result = parse_trailer(udp_payload)
    if result is not None:
        hw_id, seq = result
        return (dstport, hw_id, seq)
    # Try field-engine packet ID (first 8 bytes of payload, big-endian)
    if len(udp_payload) >= 8:
        pkt_id = struct.unpack("!Q", udp_payload[:8])[0]
        if pkt_id != 0:
            return (dstport, None, pkt_id)
    return (dstport, None, None)


class LatencyAccumulator:
    def __init__(self, window_seconds: float = 10.0):
        self._window: collections.deque[tuple[float, float]] = collections.deque()
        self._window_seconds = window_seconds
        self._last_snapshot: dict | None = None

    def add(self, latency_us: float):
        now = time.monotonic()
        self._window.append((now, latency_us))
        self._prune(now)

    def _prune(self, now: float):
        cutoff = now - self._window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def snapshot(self) -> dict:
        self._prune(time.monotonic())
        if not self._window:
            if self._last_snapshot is not None:
                return self._last_snapshot
            return {"avg_us": 0, "max_us": 0, "min_us": 0, "count": 0}
        samples = [v for _, v in self._window]
        self._last_snapshot = {
            "avg_us": sum(samples) / len(samples),
            "max_us": max(samples),
            "min_us": min(samples),
            "count": len(samples),
        }
        return self._last_snapshot


class HardwareSource:
    def __init__(self, config: Config):
        self._source_type = config.latency_source  # "nic" or "tap"
        self._sink_type = config.latency_sink       # "nic" or "tap"

        self._nic_ingress = config.nic_ingress_interface
        self._nic_egress = config.nic_egress_interface
        self._tap_ingress_iface = config.tap_ingress_interface
        self._tap_egress_iface = config.tap_egress_interface

        self._pg_ids = {s.pg_id for s in config.streams}
        self._lock = threading.Lock()
        self._stats: dict[int, LatencyAccumulator] = {
            s.pg_id: LatencyAccumulator() for s in config.streams
        }
        self._pkt_counts: dict[int, int] = {s.pg_id: 0 for s in config.streams}
        self._running = False

        self._port_to_pgid: dict[int, int] = {}
        for s in config.streams:
            if s.udp_port:
                self._port_to_pgid[s.udp_port] = s.pg_id

        self._hwid_to_pgid: dict[int, int] = {}
        self._ingress_map: dict[tuple[int, int], tuple[float, float]] = {}
        # Per-port FIFO for matching packets without trailer (STLFlowStats)
        self._ingress_port_queues: dict[int, collections.deque] = {
            port: collections.deque() for port in self._port_to_pgid
        }
        self._ingress_lock = threading.Lock()
        self._matched_count = 0
        self._ingress_count = 0
        self._egress_count = 0

    def _get_ptp_clock_dev(self, iface: str) -> str | None:
        """Get /dev/ptpN for a NIC interface."""
        try:
            result = subprocess.run(
                ["ethtool", "-T", iface],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "PTP Hardware Clock" in line:
                    num = line.strip().split(":")[-1].strip()
                    return f"/dev/ptp{num}"
        except Exception as e:
            log.warning("Could not get PTP clock for %s: %s", iface, e)
        return None

    def start(self, phc2sys_warmup: float = 5.0):
        self._running = True
        self._phc2sys_procs: list = []

        # Start phc2sys for NIC endpoints
        if self._source_type == "nic" and self._sink_type == "nic":
            # Both NICs: sync egress clock directly to ingress clock (no CLOCK_REALTIME middleman)
            ingress_ptp = self._get_ptp_clock_dev(self._nic_ingress)
            egress_ptp = self._get_ptp_clock_dev(self._nic_egress)
            if ingress_ptp and egress_ptp:
                threading.Thread(
                    target=self._phc2sys_direct_loop,
                    args=(ingress_ptp, egress_ptp),
                    daemon=True,
                ).start()
            else:
                log.warning("Could not detect PTP clocks, falling back to CLOCK_REALTIME sync")
                for iface in [self._nic_ingress, self._nic_egress]:
                    threading.Thread(target=self._phc2sys_loop, args=(iface,), daemon=True).start()
        else:
            # Single NIC: sync to CLOCK_REALTIME
            if self._source_type == "nic" and self._nic_ingress:
                threading.Thread(target=self._phc2sys_loop, args=(self._nic_ingress,), daemon=True).start()
            if self._sink_type == "nic" and self._nic_egress:
                threading.Thread(target=self._phc2sys_loop, args=(self._nic_egress,), daemon=True).start()

        if self._source_type == "nic" or self._sink_type == "nic":
            log.info("Waiting %.0fs for phc2sys to stabilize...", phc2sys_warmup)
            time.sleep(phc2sys_warmup)

        # Start capture threads
        if self._source_type == "nic":
            threading.Thread(target=self._tcpdump_capture,
                             args=(self._nic_ingress, "ingress", self._on_ingress),
                             daemon=True).start()
        elif self._source_type == "tap":
            threading.Thread(target=self._tap_capture,
                             args=(self._tap_ingress_iface, "ingress", self._on_ingress),
                             daemon=True).start()

        if self._sink_type == "nic":
            threading.Thread(target=self._tcpdump_capture,
                             args=(self._nic_egress, "egress", self._on_egress),
                             daemon=True).start()
        elif self._sink_type == "tap":
            threading.Thread(target=self._tap_capture,
                             args=(self._tap_egress_iface, "egress", self._on_egress),
                             daemon=True).start()

        threading.Thread(target=self._cleanup_loop, daemon=True).start()

        log.info("Hardware latency: source=%s sink=%s", self._source_type, self._sink_type)

    def stop(self):
        self._running = False
        for p in self._phc2sys_procs:
            try:
                p.terminate()
            except Exception:
                pass

    def get_latency_stats(self) -> dict:
        with self._lock:
            result = {}
            for pg_id, acc in self._stats.items():
                snap = acc.snapshot()
                snap["pkt_count"] = self._pkt_counts.get(pg_id, 0)
                result[pg_id] = snap
            return result

    # --- phc2sys ---

    def _phc2sys_direct_loop(self, source_ptp: str, sink_ptp: str):
        """Sync egress NIC clock directly to ingress NIC clock."""
        while self._running:
            try:
                cmd = [
                    "phc2sys",
                    "-s", source_ptp,
                    "-c", sink_ptp,
                    "-m", "-O", "0",
                    "-R", "100",
                ]
                log.info("Starting phc2sys (direct NIC-to-NIC): %s -> %s", source_ptp, sink_ptp)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self._phc2sys_procs.append(proc)
                logged = 0
                for line in proc.stdout:
                    if not self._running:
                        break
                    if line.strip() and logged < 5:
                        log.info("phc2sys: %s", line.strip())
                        logged += 1
                proc.wait()
                if self._running:
                    log.warning("phc2sys exited with %d", proc.returncode)
            except Exception as e:
                log.warning("phc2sys error (retry in 5s): %s", e)
                time.sleep(5)

    def _phc2sys_loop(self, iface: str):
        while self._running:
            try:
                cmd = ["phc2sys", "-s", "CLOCK_REALTIME", "-c", iface, "-m", "-O", "0"]
                log.info("Starting phc2sys: %s", " ".join(cmd))
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self._phc2sys_procs.append(proc)
                logged = 0
                for line in proc.stdout:
                    if not self._running:
                        break
                    if line.strip() and logged < 3:
                        log.info("phc2sys(%s): %s", iface, line.strip())
                        logged += 1
                proc.wait()
                if self._running:
                    log.warning("phc2sys(%s) exited with %d", iface, proc.returncode)
            except Exception as e:
                log.warning("phc2sys(%s) error (retry in 5s): %s", iface, e)
                time.sleep(5)

    # --- tcpdump capture (for nic mode) ---

    def _tcpdump_capture(self, iface: str, label: str, callback):
        while self._running:
            try:
                cmd = [
                    "tcpdump", "-i", iface,
                    "-j", "adapter",
                    "--time-stamp-precision=nano",
                    "-w", "-", "-U", "--immediate-mode",
                    "-B", "4096",
                    "udp or (vlan and udp)",
                ]
                log.info("Starting %s tcpdump on %s", label, iface)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                fd = proc.stdout.fileno()
                buf = bytearray()

                # Read global pcap header
                while len(buf) < PCAP_GLOBAL_HDR_SIZE:
                    chunk = os.read(fd, PCAP_GLOBAL_HDR_SIZE - len(buf))
                    if not chunk:
                        continue
                    buf.extend(chunk)
                ts_nano = struct.unpack("<I", buf[:4])[0] == 0xa1b23c4d
                ts_div = 1e9 if ts_nano else 1e6
                del buf[:PCAP_GLOBAL_HDR_SIZE]
                log.info("%s pcap: nano=%s buf_after_ghdr=%d", label.capitalize(), ts_nano, len(buf))

                dbg_reads = 0
                dbg_pkts = 0
                dbg_parsed = 0
                while self._running:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        log.info("%s: os.read returned empty (EOF)", label)
                        break
                    buf.extend(chunk)
                    dbg_reads += 1

                    if dbg_reads <= 3:
                        log.info("%s: read #%d: %d bytes, buf=%d",
                                 label, dbg_reads, len(chunk), len(buf))

                    while len(buf) >= PCAP_PKT_HDR_SIZE:
                        ts_sec, ts_frac, incl_len, _ = struct.unpack_from("<IIII", buf, 0)
                        total = PCAP_PKT_HDR_SIZE + incl_len

                        if incl_len > 65535:
                            log.warning("%s: bad incl_len=%d, resetting buffer", label, incl_len)
                            buf.clear()
                            break

                        if len(buf) < total:
                            break

                        hw_ts = ts_sec + ts_frac / ts_div
                        pkt_data = bytes(buf[PCAP_PKT_HDR_SIZE:total])
                        del buf[:total]
                        dbg_pkts += 1

                        parsed = parse_packet(pkt_data)
                        if parsed:
                            dbg_parsed += 1
                            callback(hw_ts, *parsed)
                        elif dbg_pkts <= 3:
                            et = struct.unpack("!H", pkt_data[12:14])[0] if len(pkt_data) >= 14 else 0
                            tail = pkt_data[-20:].hex() if len(pkt_data) >= 20 else pkt_data.hex()
                            # Also show what parse_packet sees for UDP payload
                            ip_off = 18 if et == 0x8100 else 14
                            pay_off = ip_off + 20 + 8
                            pay_tail = pkt_data[-20:].hex()
                            udp_port = struct.unpack("!H", pkt_data[ip_off+20+2:ip_off+20+4])[0] if len(pkt_data) > ip_off+24 else 0
                            log.info("%s: parse fail pkt #%d len=%d etype=0x%04x port=%d tail=%s",
                                     label, dbg_pkts, len(pkt_data), et, udp_port, tail)

                    if dbg_reads == 10:
                        log.info("%s: after 10 reads: pkts=%d parsed=%d buf=%d",
                                 label, dbg_pkts, dbg_parsed, len(buf))

                proc.wait()
                if proc.returncode and self._running:
                    stderr = proc.stderr.read()
                    log.warning("%s tcpdump exited: %s", label, stderr[:300])
            except Exception as e:
                log.warning("%s tcpdump error (retry in 5s): %s", label, e)
                time.sleep(5)

    # --- tshark pcapng capture (for tap/extcap mode) ---

    def _tap_capture(self, iface: str, label: str, callback):
        """Capture via tshark writing pcapng to stdout — no text dissection overhead."""
        while self._running:
            try:
                cmd = ["tshark", "-i", iface, "-w", "-", "-q"]
                log.info("Starting %s tshark (pcapng) on %s", label, iface)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                fd = proc.stdout.fileno()
                buf = bytearray()
                ts_resol = 1e6  # default: microseconds

                dbg_reads = 0
                dbg_pkts = 0
                dbg_parsed = 0

                while self._running:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        log.info("%s: os.read returned empty (EOF)", label)
                        break
                    buf.extend(chunk)
                    dbg_reads += 1

                    if dbg_reads <= 3:
                        log.info("%s: read #%d: %d bytes, buf=%d",
                                 label, dbg_reads, len(chunk), len(buf))

                    # Process complete pcapng blocks
                    while len(buf) >= PCAPNG_BLOCK_HDR_SIZE:
                        block_type, block_len = struct.unpack_from("<II", buf, 0)

                        # SHB has a special byte-order magic at offset 8
                        if block_type == PCAPNG_SHB and block_len < 12:
                            break

                        if block_len < PCAPNG_BLOCK_HDR_SIZE or block_len > 1 << 24:
                            log.warning("%s: bad pcapng block_len=%d type=0x%08x, resetting",
                                        label, block_len, block_type)
                            buf.clear()
                            break

                        if len(buf) < block_len:
                            break  # need more data

                        block_body = buf[PCAPNG_BLOCK_HDR_SIZE:block_len - 4]

                        if block_type == PCAPNG_IDB and len(block_body) >= 8:
                            # Check for if_tsresol option
                            # IDB body: link_type(2) + reserved(2) + snaplen(4) + options...
                            opts = block_body[8:]
                            while len(opts) >= 4:
                                opt_code, opt_len = struct.unpack_from("<HH", opts, 0)
                                if opt_code == 0:  # opt_endofopt
                                    break
                                if opt_code == 9 and opt_len >= 1:  # if_tsresol
                                    resol_byte = opts[4]
                                    if resol_byte & 0x80:
                                        ts_resol = 2 ** (resol_byte & 0x7F)
                                    else:
                                        ts_resol = 10 ** resol_byte
                                    log.info("%s: pcapng ts_resol=%g", label, ts_resol)
                                padded = opt_len + (4 - opt_len % 4) % 4
                                opts = opts[4 + padded:]

                        elif block_type == PCAPNG_EPB and len(block_body) >= 20:
                            # EPB: iface_id(4) + ts_high(4) + ts_low(4) + cap_len(4) + orig_len(4) + data...
                            ts_high, ts_low, cap_len = struct.unpack_from("<III", block_body, 4)
                            ts_raw = (ts_high << 32) | ts_low
                            hw_ts = ts_raw / ts_resol
                            pkt_data = bytes(block_body[20:20 + cap_len])
                            dbg_pkts += 1

                            parsed = parse_packet(pkt_data)
                            if parsed:
                                dbg_parsed += 1
                                callback(hw_ts, *parsed)
                            elif dbg_pkts <= 3:
                                et = struct.unpack("!H", pkt_data[12:14])[0] if len(pkt_data) >= 14 else 0
                                log.info("%s: parse fail pkt #%d len=%d etype=0x%04x",
                                         label, dbg_pkts, len(pkt_data), et)

                        del buf[:block_len]

                    if dbg_reads == 10:
                        log.info("%s: after 10 reads: pkts=%d parsed=%d buf=%d",
                                 label, dbg_pkts, dbg_parsed, len(buf))

                proc.wait()
                if proc.returncode and self._running:
                    stderr = proc.stderr.read()
                    log.warning("%s tshark exited: %s", label, stderr[:300])
            except Exception as e:
                log.warning("%s tshark error (retry in 5s): %s", label, e)
                time.sleep(5)

    # --- Packet callbacks ---

    def _make_key(self, dstport: int, hw_id: int | None, seq: int | None):
        """Build a map key from packet identifiers."""
        if hw_id is not None:
            return (hw_id, seq)
        if seq is not None:
            return (dstport, seq)
        return None

    def _on_packet(self, side: str, ts: float, dstport: int, hw_id: int | None, seq: int | None):
        """Handle a packet from either side.  Whichever side arrives first
        stores its timestamp; the second side matches and computes latency."""
        if side == "ingress":
            self._ingress_count += 1
        else:
            self._egress_count += 1

        if hw_id is not None and hw_id not in self._hwid_to_pgid and dstport in self._port_to_pgid:
            self._hwid_to_pgid[hw_id] = self._port_to_pgid[dstport]
            log.info("%s: hw_id %d -> pg_id %d (port %d)", side.capitalize(), hw_id, self._hwid_to_pgid[hw_id], dstport)

        pg_id = self._hwid_to_pgid.get(hw_id) if hw_id is not None else self._port_to_pgid.get(dstport)
        if pg_id is None or pg_id not in self._pg_ids:
            return

        key = self._make_key(dstport, hw_id, seq)
        if key is None:
            return

        with self._ingress_lock:
            existing = self._ingress_map.pop(key, None)
            if existing is None:
                # First side to see this packet — store it
                self._ingress_map[key] = (side, ts, time.monotonic())
                if (self._ingress_count + self._egress_count) <= 10:
                    log.info("%s #%d: hw_id=%s seq=%s port=%d ts=%.9f",
                             side.capitalize(), self._ingress_count if side == "ingress" else self._egress_count,
                             hw_id, seq, dstport, ts)
                return
            stored_side, stored_ts, _ = existing

        # Second side arrived — compute latency
        if stored_side == side:
            # Same side saw it twice (shouldn't happen with unique IDs) — re-store
            with self._ingress_lock:
                self._ingress_map[key] = (side, ts, time.monotonic())
            return

        ingress_ts = stored_ts if stored_side == "ingress" else ts
        egress_ts = ts if stored_side == "ingress" else stored_ts
        latency_us = (egress_ts - ingress_ts) * 1_000_000

        self._matched_count += 1

        if self._matched_count <= 10:
            log.info("Match #%d: pg_id=%d port=%d ingress=%.9f egress=%.9f lat=%.1f us",
                     self._matched_count, pg_id, dstport, ingress_ts, egress_ts, latency_us)

        with self._lock:
            self._pkt_counts[pg_id] = self._pkt_counts.get(pg_id, 0) + 1
            if pg_id in self._stats:
                self._stats[pg_id].add(latency_us)

    def _on_ingress(self, ts: float, dstport: int, hw_id: int | None, seq: int | None):
        self._on_packet("ingress", ts, dstport, hw_id, seq)

    def _on_egress(self, ts: float, dstport: int, hw_id: int | None, seq: int | None):
        self._on_packet("egress", ts, dstport, hw_id, seq)

    # --- Helpers ---

    def _read_exact(self, stream, n: int) -> bytes | None:
        buf = b""
        while len(buf) < n:
            chunk = stream.read(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _cleanup_loop(self):
        while self._running:
            time.sleep(2)
            now = time.monotonic()
            expired = 0
            with self._ingress_lock:
                to_remove = [k for k, (*_, t) in self._ingress_map.items()
                             if now - t > INGRESS_TTL]
                expired = len(to_remove)
                for k in to_remove:
                    del self._ingress_map[k]
                map_size = len(self._ingress_map)
                # Also expire stale entries from port FIFO queues
                for q in self._ingress_port_queues.values():
                    while q and now - q[0][1] > INGRESS_TTL:
                        q.popleft()
                        expired += 1
                    map_size += len(q)
            log.info("Stats: ingress=%d egress=%d matched=%d map_size=%d expired=%d",
                     self._ingress_count, self._egress_count, self._matched_count,
                     map_size, expired)