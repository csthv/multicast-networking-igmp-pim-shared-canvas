# -*- coding: utf-8 -*-
"""
mcast_canvas_paint.py  (Phase 2+ - Shared Multicast Canvas, Paint-like UI)

One program for every host (Upstream + Downstream):
- Tkinter GUI "paint" canvas for drawing.
- Sends drawing events via UDP multicast.
- Receives drawing events via UDP multicast and renders them.
- No server; full peer-to-peer synchronization via multicast.

Keeps all originally implemented features:
- UDP + Multicast (group/port configurable)
- TTL configurable
- Canvas events -> multicast UDP packets
- Receive+parse -> draw
- Professional UI + Clear broadcast + Save .ps + presence hello/bye
- Optional IGMPv2 JOIN/LEAVE periodically via Scapy (for Wireshark visibility)
- Optional "Peer Unicast Assist" (--peer-unicast) to fix common IGMP-proxy one-way multicast.
  Still sends multicast (requirement), but also unicasts to known peers learned from HELLO/traffic.
  Includes deduplication to avoid double drawing.

Adds / Improves:
- Shared UNDO/REDO across all instances (distributed, deterministic):
  * Undo/Redo commands are broadcast and applied everywhere.
  * Undo targets a specific op_id, so everyone undoes the same operation.
  * Redo targets the most recently undone operation (deterministic).
  * New drawing operations clear redo (Paint-like).
- Bucket Fill now behaves like Paint for vector shapes:
  * If you click inside a rectangle/oval/polygon item, only that shape is filled (undoable, broadcast).
  * If you click on empty canvas, it fills background (undoable, broadcast).
  * (True raster flood-fill is intentionally not implemented to keep the vector/multicast model lightweight.)
- Color swap arrow button + Paint-like mouse behavior:
  * Left mouse uses Primary color.
  * Right mouse uses Secondary color.
  * Color Picker: Left picks Primary, Right picks Secondary.
  * Bucket: Left fills with Primary, Right fills with Secondary.
  * Swap button (⇄) and 'X' hotkey swap colors.
- Richer statistics + operation history log (TX/RX):
  * Live send/recv pkt/s and KB/s + totals, plus last RX info.
  * History list shows strokes/shapes/text/fill/bg/undo/redo/clear events.
- More classic "old Paint" look:
  * Menubar (File/Edit)
  * Toolbar-like tool buttons, classic separators, compact layout

Notes:
- On Windows, allow UDP inbound/outbound on selected port in Firewall.
- TTL must be >= 2 to cross router (use 16 like phase 1).
- If drawings only go one direction across router, use --peer-unicast.

Author: (Your original + requested enhancements)
"""

import argparse
import json
import math
import os
import queue
import socket
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---- GUI ----
try:
    import tkinter as tk
    from tkinter import ttk, colorchooser, filedialog, messagebox
except Exception as e:
    raise SystemExit(f"Tkinter is required but not available: {e}")


# =========================
# Optional Scapy (IGMP only)
# =========================
SCAPY_OK = False
IGMP = None
IPOption_Router_Alert = None
scapy_conf = None
scapy_sendp = None
scapy_Ether = None
scapy_IP = None
scapy_get_if_list = None
scapy_get_if_addr = None
scapy_get_if_hwaddr = None

def _try_import_scapy():
    global SCAPY_OK, IGMP, IPOption_Router_Alert
    global scapy_conf, scapy_sendp, scapy_Ether, scapy_IP
    global scapy_get_if_list, scapy_get_if_addr, scapy_get_if_hwaddr

    try:
        from scapy.all import conf as _conf
        from scapy.all import sendp as _sendp
        from scapy.all import Ether as _Ether
        from scapy.all import IP as _IP
        from scapy.all import get_if_list as _get_if_list
        from scapy.all import get_if_addr as _get_if_addr
        from scapy.all import get_if_hwaddr as _get_if_hwaddr

        scapy_conf = _conf
        scapy_sendp = _sendp
        scapy_Ether = _Ether
        scapy_IP = _IP
        scapy_get_if_list = _get_if_list
        scapy_get_if_addr = _get_if_addr
        scapy_get_if_hwaddr = _get_if_hwaddr

        # IGMP layer import compatibility
        try:
            from scapy.layers.inet import IGMP as _IGMP  # type: ignore
            IGMP = _IGMP
        except Exception:
            try:
                from scapy.contrib.igmp import IGMP as _IGMP  # type: ignore
                IGMP = _IGMP
            except Exception:
                IGMP = None

        try:
            from scapy.layers.inet import IPOption_Router_Alert as _RA  # type: ignore
            IPOption_Router_Alert = _RA
        except Exception:
            IPOption_Router_Alert = None

        SCAPY_OK = True
    except Exception:
        SCAPY_OK = False


# =========================
# Utilities
# =========================

def now_ms() -> int:
    return int(time.time() * 1000)

def fmt_hhmmss(ts_ms: int) -> str:
    try:
        t = time.localtime(ts_ms / 1000.0)
        return time.strftime("%H:%M:%S", t)
    except Exception:
        return "--:--:--"

def guess_local_ip() -> Optional[str]:
    """
    Try to guess the local IPv4 by using the route table (UDP connect trick).
    """
    test_targets = [("8.8.8.8", 80), ("1.1.1.1", 80)]
    for host, port in test_targets:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((host, port))
            ip = s.getsockname()[0]
            if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
    return None

def multicast_mac(ip_str: str) -> str:
    """
    Convert IPv4 multicast (224.0.0.0/4) to Ethernet MAC 01:00:5e:xx:xx:xx
    """
    parts = ip_str.split(".")
    if len(parts) != 4:
        return "01:00:5e:00:00:00"
    ip = (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
    return "01:00:5e:%02x:%02x:%02x" % ((ip >> 16) & 0x7F, (ip >> 8) & 0xFF, ip & 0xFF)

def downsample_points(points: List[List[float]], max_points: int) -> List[List[float]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    step = len(points) / float(max_points)
    out: List[List[float]] = []
    i = 0.0
    while int(i) < len(points) and len(out) < max_points:
        out.append(points[int(i)])
        i += step
    if out and out[-1] != points[-1]:
        out.append(points[-1])
    return out

def clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# =========================
# Socket-based Multicast Transport (DATA PLANE)
# =========================

class MulticastTransport:
    """
    UDP multicast send/receive using Python sockets (Phase 2 requirement).
    Adds stats counters + optional peer-unicast assist.
    """
    def __init__(
        self,
        group: str,
        port: int,
        ttl: int,
        ifaddr: str,
        loopback: bool,
        debug: bool = False
    ):
        self.group = group
        self.port = int(port)
        self.ttl = int(ttl)
        self.ifaddr = ifaddr
        self.loopback = bool(loopback)
        self.debug = debug

        self._lock = threading.Lock()
        self._sent_pkts = 0
        self._sent_bytes = 0
        self._recv_pkts = 0
        self._recv_bytes = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass

        # Larger buffers help in bursty drawing
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)
        except Exception:
            pass

        # Bind for receiving (Windows: ("", port) works)
        self.sock.bind(("", self.port))

        group_bin = socket.inet_aton(self.group)
        ifaddr_bin = socket.inet_aton(self.ifaddr)

        # Join group on specific interface
        mreq = struct.pack("4s4s", group_bin, ifaddr_bin)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Outgoing interface and TTL
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, ifaddr_bin)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("B", self.ttl))

        # Loopback controls whether you receive your own multicast
        try:
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, struct.pack("B", 1 if self.loopback else 0))
        except Exception:
            try:
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1 if self.loopback else 0)
            except Exception:
                pass

        self.sock.settimeout(1.0)
        self._closed = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            group_bin = socket.inet_aton(self.group)
            ifaddr_bin = socket.inet_aton(self.ifaddr)
            mreq = struct.pack("4s4s", group_bin, ifaddr_bin)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def get_counters(self) -> Tuple[int, int, int, int]:
        with self._lock:
            return self._sent_pkts, self._sent_bytes, self._recv_pkts, self._recv_bytes

    def _count_send(self, n: int):
        with self._lock:
            self._sent_pkts += 1
            self._sent_bytes += n

    def _count_recv(self, n: int):
        with self._lock:
            self._recv_pkts += 1
            self._recv_bytes += n

    def send_raw(self, data: bytes, addr: Tuple[str, int]):
        try:
            self.sock.sendto(data, addr)
            self._count_send(len(data))
        except Exception as e:
            if self.debug:
                print(f"[NET] send failed to {addr}: {e}")

    def send_multicast(self, obj: Dict[str, Any]):
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8", errors="ignore")
        self.send_raw(data, (self.group, self.port))

    def send_unicast(self, obj: Dict[str, Any], ip: str, port: Optional[int] = None):
        p = self.port if port is None else int(port)
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8", errors="ignore")
        self.send_raw(data, (ip, p))

    def recv_once(self) -> Optional[Tuple[Dict[str, Any], Tuple[str, int]]]:
        try:
            data, addr = self.sock.recvfrom(65535)
        except socket.timeout:
            return None
        except OSError:
            return None
        except Exception:
            return None

        self._count_recv(len(data))
        try:
            obj = json.loads(data.decode("utf-8", errors="ignore"))
            if isinstance(obj, dict):
                return obj, addr
        except Exception:
            return None
        return None


# =========================
# Optional Scapy-based IGMP helper
# =========================

class ScapyIGMPKeepalive:
    """
    Periodically send IGMPv2 Membership Report (JOIN) using scapy,
    and send IGMPv2 Leave on stop.

    Optional: helps show IGMP in Wireshark + keep membership state alive.
    Data plane stays socket-based.
    """
    def __init__(self, ifaddr: str, group: str, interval_s: int, scapy_iface: Optional[str], debug: bool = False):
        self.ifaddr = ifaddr
        self.group = group
        self.interval_s = max(1, int(interval_s))
        self.scapy_iface = scapy_iface
        self.debug = debug

        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

        if not SCAPY_OK or IGMP is None:
            raise RuntimeError("Scapy IGMP support is not available. Install/upgrade scapy and Npcap.")

        try:
            scapy_conf.use_pcap = True
        except Exception:
            pass

        self.iface = self._pick_iface()
        self.src_ip = self.ifaddr
        self.src_mac = scapy_get_if_hwaddr(self.iface)

    def _pick_iface(self) -> str:
        if self.scapy_iface:
            key = self.scapy_iface.strip().lower()
            for n in scapy_get_if_list():
                if key in n.lower():
                    return n
            raise RuntimeError(f"Could not match scapy iface '{self.scapy_iface}'. Use --list-ifaces.")

        for n in scapy_get_if_list():
            try:
                if scapy_get_if_addr(n) == self.ifaddr:
                    return n
            except Exception:
                pass

        raise RuntimeError(
            f"Could not auto-match a scapy interface for ifaddr={self.ifaddr}. "
            f"Use --list-ifaces and pass --scapy-iface."
        )

    def _ip_with_router_alert(self, dst_ip: str) -> Any:
        if IPOption_Router_Alert is not None:
            return scapy_IP(src=self.src_ip, dst=dst_ip, ttl=1, options=[IPOption_Router_Alert()])
        return scapy_IP(src=self.src_ip, dst=dst_ip, ttl=1)

    def _build_join(self) -> Any:
        dst_mac = multicast_mac(self.group)
        return (
            scapy_Ether(src=self.src_mac, dst=dst_mac) /
            self._ip_with_router_alert(self.group) /
            IGMP(type=0x16, gaddr=self.group)
        )

    def _build_leave(self) -> Any:
        leave_dst = "224.0.0.2"
        dst_mac = multicast_mac(leave_dst)
        return (
            scapy_Ether(src=self.src_mac, dst=dst_mac) /
            self._ip_with_router_alert(leave_dst) /
            IGMP(type=0x17, gaddr=self.group)
        )

    def _sendp(self, pkt: Any):
        scapy_sendp(pkt, iface=self.iface, verbose=False)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_evt.set()
        try:
            pkt = self._build_leave()
            self._sendp(pkt)
            if self.debug:
                print(f"[IGMP] LEAVE sent: {self.group} via {self.iface}")
        except Exception as e:
            if self.debug:
                print(f"[IGMP] LEAVE failed (ignored): {e}")

    def _loop(self):
        try:
            pkt = self._build_join()
            self._sendp(pkt)
            if self.debug:
                print(f"[IGMP] JOIN sent: {self.group} via {self.iface}")
        except Exception as e:
            if self.debug:
                print(f"[IGMP] JOIN failed: {e}")

        while not self.stop_evt.wait(self.interval_s):
            try:
                pkt = self._build_join()
                self._sendp(pkt)
                if self.debug:
                    print(f"[IGMP] JOIN keepalive sent: {self.group}")
            except Exception as e:
                if self.debug:
                    print(f"[IGMP] JOIN keepalive failed: {e}")


# =========================
# App Configuration
# =========================

@dataclass
class AppConfig:
    group: str
    port: int
    ttl: int
    ifaddr: str
    username: str

    # UI defaults
    bg: str
    primary_color: str
    secondary_color: str
    pen_width: int
    brush_width: int
    eraser_width: int
    text_size: int

    # net/tuning
    min_step_px: int
    max_stroke_points: int
    max_packet_bytes: int
    presence_interval_s: int
    stats_interval_ms: int

    # options
    peer_unicast: bool
    loopback: bool
    igmp_enable: bool
    igmp_interval_s: int
    scapy_iface: Optional[str]
    debug: bool


# =========================
# Shared Canvas Application (Paint-like)
# =========================

class MulticastPaintApp:
    MSG_VERSION = 1
    SEEN_MAX = 6000

    TOOL_PENCIL = "pencil"
    TOOL_BRUSH = "brush"
    TOOL_ERASER = "eraser"
    TOOL_LINE = "line"
    TOOL_RECT = "rect"
    TOOL_OVAL = "oval"
    TOOL_TEXT = "text"
    TOOL_PICKER = "picker"
    TOOL_BUCKET = "bucket"  # fill shapes or background (undoable)

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

        # identity
        self.client_id = str(uuid.uuid4())

        # Lamport clock (helps deterministic-ish ordering metadata; undo/redo targets op_id explicitly)
        self.lamport = 0

        # network
        self.transport = MulticastTransport(
            group=cfg.group,
            port=cfg.port,
            ttl=cfg.ttl,
            ifaddr=cfg.ifaddr,
            loopback=cfg.loopback,
            debug=cfg.debug,
        )

        # optional IGMP keepalive (Scapy)
        self.igmp: Optional[ScapyIGMPKeepalive] = None
        if cfg.igmp_enable:
            if not SCAPY_OK:
                raise RuntimeError("Scapy not available but --igmp was requested.")
            if IGMP is None:
                raise RuntimeError("Scapy IGMP layer not available (upgrade scapy).")
            self.igmp = ScapyIGMPKeepalive(
                ifaddr=cfg.ifaddr,
                group=cfg.group,
                interval_s=cfg.igmp_interval_s,
                scapy_iface=cfg.scapy_iface,
                debug=cfg.debug,
            )
            self.igmp.start()

        # receiver thread communication
        self.net_queue: "queue.Queue[Tuple[Dict[str, Any], Tuple[str, int]]]" = queue.Queue()
        self.stop_evt = threading.Event()
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

        # de-duplication for multicast+unicast duplicates
        self._seen_set = set()
        self._seen_q: deque[str] = deque(maxlen=self.SEEN_MAX)

        # peers: client_id -> dict(username,last_seen_ms,ip,port)
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.last_rx: str = "—"

        # operations: op_id -> dict
        # Each entry:
        #   {
        #     "msg": original message dict,
        #     "items": [canvas item ids] (for create ops),
        #     "active": bool,
        #     "kind": "create" | "fill" | "bg",
        #     "created_key": (lc, sender_id, op_id),
        #     "undone_key": (lc, sender_id, mid) or None,
        #     "meta": {...}
        #   }
        self.ops: Dict[str, Dict[str, Any]] = {}
        self.item_to_op: Dict[int, str] = {}  # canvas item id -> op_id (helps bucket fill)
        self.pending_undo: Dict[str, Tuple[int, str, str]] = {}  # op_id -> cmd_key
        self.pending_redo: Dict[str, Dict[str, Any]] = {}  # op_id -> payload (rare)

        # stroke temp items (local & remote)
        self.local_stroke_id: Optional[str] = None
        self.local_points: List[List[float]] = []
        self.local_last_px: Optional[Tuple[int, int]] = None
        self.local_seq = 0
        self.local_temp_items: List[int] = []

        self.remote_temp_items: Dict[str, List[int]] = {}  # stroke_id -> temp segment items
        self.remote_final: Dict[str, int] = {}            # stroke_id -> final time (for late segments ignore)

        # shape preview
        self.shape_start_px: Optional[Tuple[int, int]] = None
        self.shape_preview_item: Optional[int] = None

        # UI state
        self.root = tk.Tk()
        self.root.title(self._window_title())
        self.root.geometry("1280x780")
        self.root.minsize(1040, 660)

        self.tool_var = tk.StringVar(value=self.TOOL_PENCIL)
        self.fill_var = tk.BooleanVar(value=False)
        self.smooth_var = tk.BooleanVar(value=True)

        self.primary_var = tk.StringVar(value=self.cfg.primary_color)
        self.secondary_var = tk.StringVar(value=self.cfg.secondary_color)

        self.width_var = tk.IntVar(value=self.cfg.pen_width)
        self.text_size_var = tk.IntVar(value=self.cfg.text_size)

        self._active_mouse_button = 1  # 1=left(primary), 3=right(secondary)

        # stats snapshot
        self._last_stats_t = time.time()
        self._last_sent_pkts = 0
        self._last_sent_bytes = 0
        self._last_recv_pkts = 0
        self._last_recv_bytes = 0
        self._send_rate = "0.0 pkt/s, 0.0 KB/s"
        self._recv_rate = "0.0 pkt/s, 0.0 KB/s"
        self._send_total = "0 pkts, 0 KB"
        self._recv_total = "0 pkts, 0 KB"

        # history log
        self._history_max = 600
        self._history: deque[str] = deque(maxlen=self._history_max)

        # build UI
        self._build_ui()
        self._bind_events()

        # periodic tasks
        self._schedule_queue_pump()
        self._schedule_presence()
        self._schedule_peer_prune()
        self._schedule_stats()

        # send initial presence
        self._send_hello()

        # close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --------------------------
    # Lamport + message helpers
    # --------------------------
    def _tick_lamport(self, remote_lc: Optional[int] = None) -> int:
        if isinstance(remote_lc, int):
            self.lamport = max(self.lamport, remote_lc) + 1
        else:
            self.lamport += 1
        return self.lamport

    def _new_mid(self) -> str:
        return uuid.uuid4().hex

    def _created_key_from_msg(self, msg: Dict[str, Any]) -> Tuple[int, str, str]:
        # Deterministic-ish ordering key for operations
        try:
            lc = int(msg.get("lc", 0))
        except Exception:
            lc = 0
        sid = str(msg.get("id", ""))
        op = str(msg.get("op", ""))
        return (lc, sid, op)

    def _cmd_key_from_msg(self, msg: Dict[str, Any]) -> Tuple[int, str, str]:
        # Ordering key for undo/redo commands (mostly for "most recently undone")
        try:
            lc = int(msg.get("lc", 0))
        except Exception:
            lc = 0
        sid = str(msg.get("id", ""))
        mid = str(msg.get("mid", ""))
        return (lc, sid, mid)

    # --------------------------
    # UI
    # --------------------------
    def _window_title(self) -> str:
        return f"Multicast Paint | {self.cfg.username} | IF {self.cfg.ifaddr} | {self.cfg.group}:{self.cfg.port} TTL={self.cfg.ttl}"

    def _build_ui(self):
        style = ttk.Style()
        themes = style.theme_names()
        # Choose a more "classic" feel when possible.
        for pref in ("classic", "vista", "xpnative", "clam", "alt", "default"):
            if pref in themes:
                try:
                    style.theme_use(pref)
                    break
                except Exception:
                    pass

        # Menubar (old paint feel)
        menubar = tk.Menu(self.root)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Save As… (.ps)", command=self._save_postscript)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=m_file)

        m_edit = tk.Menu(menubar, tearoff=0)
        m_edit.add_command(label="Undo\tCtrl+Z", command=self._undo_shared)
        m_edit.add_command(label="Redo\tCtrl+Y", command=self._redo_shared)
        m_edit.add_separator()
        m_edit.add_command(label="New (Local)", command=self._new_local)
        m_edit.add_command(label="Clear (Broadcast)\tCtrl+L", command=self._clear_broadcast)
        menubar.add_cascade(label="Edit", menu=m_edit)

        self.root.config(menu=menubar)

        # Toolbar/top bar
        top = ttk.Frame(self.root, padding=(8, 6))
        top.pack(side=tk.TOP, fill=tk.X)

        self.net_info_lbl = ttk.Label(
            top,
            text=f"Group {self.cfg.group}:{self.cfg.port}   TTL {self.cfg.ttl}   IF {self.cfg.ifaddr}   UnicastAssist={'ON' if self.cfg.peer_unicast else 'OFF'}",
        )
        self.net_info_lbl.pack(side=tk.LEFT)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(top, text="New", command=self._new_local).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="Clear All", command=self._clear_broadcast).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="Save", command=self._save_postscript).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(top, text="Undo", command=self._undo_shared).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="Redo", command=self._redo_shared).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.stats_lbl = ttk.Label(top, text="Send: 0.0 pkt/s | Recv: 0.0 pkt/s")
        self.stats_lbl.pack(side=tk.LEFT)

        # Middle layout: left toolbox + canvas + right tabs
        mid = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = ttk.Frame(mid, width=250)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left.pack_propagate(False)

        center = ttk.Frame(mid)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(mid, width=310)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        right.pack_propagate(False)

        # Left: tools (toolbar-like)
        tools_box = ttk.Labelframe(left, text="Tools", padding=(8, 6))
        tools_box.pack(side=tk.TOP, fill=tk.X)

        self._tool_buttons: Dict[str, ttk.Button] = {}

        tool_defs = [
            ("✏ Pencil", self.TOOL_PENCIL),
            ("🖌 Brush", self.TOOL_BRUSH),
            ("🧽 Eraser", self.TOOL_ERASER),
            ("／ Line", self.TOOL_LINE),
            ("▭ Rect", self.TOOL_RECT),
            ("⬭ Oval", self.TOOL_OVAL),
            ("T Text", self.TOOL_TEXT),
            ("🎯 Picker", self.TOOL_PICKER),
            ("🪣 Bucket", self.TOOL_BUCKET),
        ]

        # Grid 2 columns for a classic compact feel
        for i, (label, val) in enumerate(tool_defs):
            r = i // 2
            c = i % 2
            b = ttk.Button(
                tools_box,
                text=label,
                width=12,
                command=lambda v=val: self._set_tool(v),
            )
            b.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
            self._tool_buttons[val] = b
        tools_box.grid_columnconfigure(0, weight=1)
        tools_box.grid_columnconfigure(1, weight=1)

        # Left: options
        opts_box = ttk.Labelframe(left, text="Options", padding=(8, 6))
        opts_box.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

        ttk.Label(opts_box, text="Size").pack(anchor=tk.W)
        self.size_scale = ttk.Scale(
            opts_box, from_=1, to=50, orient=tk.HORIZONTAL,
            command=lambda _: self._on_size_changed()
        )
        self.size_scale.set(self.width_var.get())
        self.size_scale.pack(fill=tk.X, pady=(0, 2))
        self.size_lbl = ttk.Label(opts_box, text=f"{self.width_var.get()} px")
        self.size_lbl.pack(anchor=tk.W)

        ttk.Checkbutton(opts_box, text="Fill shapes (use Secondary)", variable=self.fill_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Checkbutton(opts_box, text="Smooth strokes", variable=self.smooth_var).pack(anchor=tk.W)

        ttk.Label(opts_box, text="Text size").pack(anchor=tk.W, pady=(6, 0))
        self.text_spin = ttk.Spinbox(opts_box, from_=8, to=64, textvariable=self.text_size_var, width=6)
        self.text_spin.pack(anchor=tk.W)

        # Left: colors (primary + secondary + palette)
        colors_box = ttk.Labelframe(left, text="Colors", padding=(8, 6))
        colors_box.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))

        row = ttk.Frame(colors_box)
        row.pack(fill=tk.X)

        ttk.Label(row, text="Primary").pack(side=tk.LEFT)
        self.primary_preview = tk.Label(row, width=3, background=self.primary_var.get(), relief=tk.SOLID, bd=1)
        self.primary_preview.pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(row, text="Pick…", command=lambda: self._choose_color(primary=True)).pack(side=tk.LEFT)

        self.btn_swap = ttk.Button(row, text="⇄", width=3, command=self._swap_colors)
        self.btn_swap.pack(side=tk.RIGHT, padx=(6, 0))

        row2 = ttk.Frame(colors_box)
        row2.pack(fill=tk.X, pady=(6, 0))

        ttk.Label(row2, text="Secondary").pack(side=tk.LEFT)
        self.secondary_preview = tk.Label(row2, width=3, background=self.secondary_var.get(), relief=tk.SOLID, bd=1)
        self.secondary_preview.pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(row2, text="Pick…", command=lambda: self._choose_color(primary=False)).pack(side=tk.LEFT)

        ttk.Label(colors_box, text="Palette (L=Primary, R=Secondary)").pack(anchor=tk.W, pady=(8, 4))

        palette_frame = ttk.Frame(colors_box)
        palette_frame.pack(fill=tk.BOTH, expand=True)

        self._palette_colors = [
            "#000000", "#7f7f7f", "#ffffff", "#c00000", "#ff0000", "#ffc000",
            "#ffff00", "#92d050", "#00b050", "#00b0f0", "#0070c0", "#002060",
            "#7030a0", "#ff00ff", "#f4b183", "#8faadc",
            "#1f4e79", "#2f5597", "#375623", "#7f6000", "#843c0c", "#5b9bd5",
            "#70ad47", "#ed7d31"
        ]

        cols = 6
        for i, col in enumerate(self._palette_colors):
            btn = tk.Label(palette_frame, background=col, width=4, height=2, relief=tk.RAISED, bd=1, cursor="hand2")
            r = i // cols
            c = i % cols
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
            btn.bind("<Button-1>", lambda e, cc=col: self._set_primary(cc))
            btn.bind("<Button-3>", lambda e, cc=col: self._set_secondary(cc))
        for c in range(cols):
            palette_frame.grid_columnconfigure(c, weight=1)

        # Center: canvas
        self.canvas = tk.Canvas(center, background=self.cfg.bg, highlightthickness=1, highlightbackground="#808080")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Right: tabs (Peers, History)
        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True)

        peers_tab = ttk.Frame(nb, padding=(8, 6))
        hist_tab = ttk.Frame(nb, padding=(8, 6))
        nb.add(peers_tab, text="Peers")
        nb.add(hist_tab, text="History")

        # Peers tab
        self.peers_list = tk.Listbox(peers_tab, height=14)
        self.peers_list.pack(fill=tk.BOTH, expand=True)

        self.peer_details = ttk.Label(peers_tab, text="Last RX: —", wraplength=260, justify=tk.LEFT)
        self.peer_details.pack(anchor=tk.W, pady=(6, 0))

        # History tab (with scrollbar)
        hist_top = ttk.Frame(hist_tab)
        hist_top.pack(fill=tk.X)
        ttk.Button(hist_top, text="Clear Log", command=self._clear_history).pack(side=tk.LEFT)
        ttk.Button(hist_top, text="Copy Selected", command=self._copy_selected_history).pack(side=tk.LEFT, padx=(6, 0))

        self.history_list = tk.Listbox(hist_tab, height=20)
        self.history_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(6, 0))

        sb = ttk.Scrollbar(hist_tab, orient=tk.VERTICAL, command=self.history_list.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=(6, 0))
        self.history_list.configure(yscrollcommand=sb.set)

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W, padding=(8, 6))
        status.pack(side=tk.BOTTOM, fill=tk.X)

        self._refresh_tool_buttons()
        self._update_status()

    def _bind_events(self):
        # Canvas mouse (left = primary, right = secondary)
        self.canvas.bind("<ButtonPress-1>", lambda e: self._on_press(e, button=1))
        self.canvas.bind("<B1-Motion>", lambda e: self._on_move(e, button=1))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._on_release(e, button=1))

        self.canvas.bind("<ButtonPress-3>", lambda e: self._on_press(e, button=3))
        self.canvas.bind("<B3-Motion>", lambda e: self._on_move(e, button=3))
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._on_release(e, button=3))

        self.canvas.bind("<Motion>", self._on_hover)

        # Shortcuts
        self.root.bind("<Escape>", lambda e: self._on_close())
        self.root.bind("<Control-l>", lambda e: self._clear_broadcast())
        self.root.bind("<Control-z>", lambda e: self._undo_shared())
        self.root.bind("<Control-y>", lambda e: self._redo_shared())

        # Paint-like swap hotkey
        self.root.bind("<x>", lambda e: self._swap_colors())
        self.root.bind("<X>", lambda e: self._swap_colors())

    def _on_hover(self, event):
        self._update_status(coords=(event.x, event.y))

    def _on_size_changed(self):
        v = int(float(self.size_scale.get()))
        self.width_var.set(v)
        self.size_lbl.configure(text=f"{v} px")
        self._update_status()

    def _set_tool(self, tool: str):
        self.tool_var.set(tool)
        # Suggest sensible defaults when switching tools (optional, paint-like)
        try:
            if tool == self.TOOL_BRUSH and self.width_var.get() < 3:
                self.width_var.set(self.cfg.brush_width)
                self.size_scale.set(self.width_var.get())
            if tool == self.TOOL_ERASER and self.width_var.get() < 6:
                self.width_var.set(self.cfg.eraser_width)
                self.size_scale.set(self.width_var.get())
        except Exception:
            pass
        self._refresh_tool_buttons()
        self._update_status()

    def _refresh_tool_buttons(self):
        active = self.tool_var.get()
        for t, b in self._tool_buttons.items():
            try:
                # emulate pressed state
                b.state(["pressed"] if t == active else ["!pressed"])
            except Exception:
                pass

    def _choose_color(self, primary: bool):
        init = self.primary_var.get() if primary else self.secondary_var.get()
        col = colorchooser.askcolor(title="Choose color", initialcolor=init)
        if col and col[1]:
            if primary:
                self._set_primary(col[1])
            else:
                self._set_secondary(col[1])

    def _set_primary(self, c: str):
        self.primary_var.set(c)
        self.primary_preview.configure(background=c)
        self._update_status()

    def _set_secondary(self, c: str):
        self.secondary_var.set(c)
        self.secondary_preview.configure(background=c)
        self._update_status()

    def _swap_colors(self):
        p = self.primary_var.get()
        s = self.secondary_var.get()
        self.primary_var.set(s)
        self.secondary_var.set(p)
        self.primary_preview.configure(background=self.primary_var.get())
        self.secondary_preview.configure(background=self.secondary_var.get())
        self._update_status()

    def _update_peer_list_ui(self):
        self.peers_list.delete(0, tk.END)
        items = []
        now = now_ms()
        for pid, info in self.peers.items():
            age = max(0, (now - int(info.get("last", now))) // 1000)
            user = str(info.get("user", "?"))
            ip = str(info.get("ip", "?"))
            items.append((age, f"{user}  ({ip})  - {age}s ago"))
        items.sort(key=lambda x: x[0])
        for _, line in items:
            self.peers_list.insert(tk.END, line)

    def _update_status(self, coords: Optional[Tuple[int, int]] = None):
        tool = self.tool_var.get()
        fill = "ON" if self.fill_var.get() else "OFF"
        smooth = "ON" if self.smooth_var.get() else "OFF"
        w = self.width_var.get()
        p = self.primary_var.get()
        s = self.secondary_var.get()
        peer_count = len(self.peers)
        xy = ""
        if coords:
            xy = f" | X,Y=({coords[0]},{coords[1]})"
        self.status_var.set(
            f"Tool: {tool} | Size: {w}px | Fill: {fill} | Smooth: {smooth} | Primary: {p} | Secondary: {s}"
            f" | Peers: {peer_count}{xy} | TX: {self._send_rate} ({self._send_total}) | RX: {self._recv_rate} ({self._recv_total})"
        )

    # --------------------------
    # History log UI
    # --------------------------
    def _clear_history(self):
        self._history.clear()
        try:
            self.history_list.delete(0, tk.END)
        except Exception:
            pass

    def _copy_selected_history(self):
        try:
            idx = self.history_list.curselection()
            if not idx:
                return
            line = self.history_list.get(idx[0])
            self.root.clipboard_clear()
            self.root.clipboard_append(line)
        except Exception:
            pass

    def _log_event(self, direction: str, obj: Dict[str, Any], addr: Optional[Tuple[str, int]] = None):
        """
        direction: "TX" | "RX" | "LOCAL"
        """
        try:
            t = fmt_hhmmss(int(obj.get("ts", now_ms())))
        except Exception:
            t = fmt_hhmmss(now_ms())

        mtype = str(obj.get("type", "?"))
        user = str(obj.get("user", "?"))
        op = str(obj.get("op", ""))
        op_short = op[:8] if op else "—"
        extra = ""

        if mtype == "stroke":
            try:
                npts = len(obj.get("pts", []) or [])
            except Exception:
                npts = 0
            extra = f" pts={npts} w={obj.get('width')}"
        elif mtype == "shape":
            extra = f" {obj.get('shape')}"
        elif mtype == "text":
            txt = str(obj.get("text", ""))
            if len(txt) > 18:
                txt = txt[:18] + "…"
            extra = f" \"{txt}\""
        elif mtype == "fill":
            extra = f" -> {obj.get('color', '')}"
        elif mtype == "bg":
            extra = f" -> {obj.get('bg', '')}"
        elif mtype in ("undo", "redo"):
            extra = f" target={str(obj.get('target', obj.get('op', '')) )[:8]}"

        if addr and direction == "RX":
            extra += f" from {addr[0]}"
        line = f"[{t}] {direction:<5} {user:<12} {mtype:<6} op={op_short}{extra}"

        self._history.append(line)
        try:
            # Update listbox (append only)
            self.history_list.insert(tk.END, line)
            self.history_list.see(tk.END)
            # Enforce max length visually too
            if self.history_list.size() > self._history_max:
                self.history_list.delete(0)
        except Exception:
            pass

    # --------------------------
    # Coordinate normalization
    # --------------------------
    def _canvas_size(self) -> Tuple[int, int]:
        w = max(1, int(self.canvas.winfo_width()))
        h = max(1, int(self.canvas.winfo_height()))
        return w, h

    def _norm(self, x: int, y: int) -> List[float]:
        w, h = self._canvas_size()
        return [round(x / float(w), 6), round(y / float(h), 6)]

    def _denorm(self, p: List[float]) -> Tuple[int, int]:
        w, h = self._canvas_size()
        x = int(p[0] * w)
        y = int(p[1] * h)
        return x, y

    # --------------------------
    # Dedup
    # --------------------------
    def _seen(self, mid: Optional[str]) -> bool:
        if not isinstance(mid, str) or not mid:
            return False
        if mid in self._seen_set:
            return True
        self._seen_set.add(mid)
        self._seen_q.append(mid)
        # occasional cleanup
        if len(self._seen_set) > self.SEEN_MAX * 2:
            keep = set(self._seen_q)
            self._seen_set = keep
        return False

    # --------------------------
    # Network send helpers
    # --------------------------
    def _broadcast_obj(self, obj: Dict[str, Any]):
        """
        Always send multicast.
        Optionally also send unicast to known peers if --peer-unicast is enabled.
        """
        self.transport.send_multicast(obj)

        if not self.cfg.peer_unicast:
            return

        # Unicast assist: send to known peer IPs too (helps when multicast is one-way).
        for pid, info in list(self.peers.items()):
            ip = info.get("ip")
            port = info.get("port", self.cfg.port)
            if isinstance(ip, str) and ip and pid != self.client_id:
                self.transport.send_unicast(obj, ip, int(port))

    # --------------------------
    # Presence
    # --------------------------
    def _send_hello(self):
        self._tick_lamport()
        hello = {
            "v": self.MSG_VERSION,
            "type": "hello",
            "mid": self._new_mid(),
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "port": self.cfg.port,
            "lc": self.lamport,
        }
        self._broadcast_obj(hello)

    def _send_bye(self):
        self._tick_lamport()
        bye = {
            "v": self.MSG_VERSION,
            "type": "bye",
            "mid": self._new_mid(),
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "port": self.cfg.port,
            "lc": self.lamport,
        }
        self._broadcast_obj(bye)

    def _schedule_presence(self):
        self._send_hello()
        self.root.after(int(self.cfg.presence_interval_s * 1000), self._schedule_presence)

    def _schedule_peer_prune(self):
        cutoff = now_ms() - 30000
        dead = [pid for pid, info in self.peers.items() if int(info.get("last", 0)) < cutoff]
        for pid in dead:
            self.peers.pop(pid, None)
        self._update_peer_list_ui()
        self._update_status()
        self.root.after(2000, self._schedule_peer_prune)

    # --------------------------
    # Stats
    # --------------------------
    def _schedule_stats(self):
        self._update_stats()
        self.root.after(self.cfg.stats_interval_ms, self._schedule_stats)

    def _update_stats(self):
        sent_pkts, sent_bytes, recv_pkts, recv_bytes = self.transport.get_counters()
        t = time.time()
        dt = max(0.001, t - self._last_stats_t)

        ds_pkts = sent_pkts - self._last_sent_pkts
        ds_bytes = sent_bytes - self._last_sent_bytes
        dr_pkts = recv_pkts - self._last_recv_pkts
        dr_bytes = recv_bytes - self._last_recv_bytes

        sp = ds_pkts / dt
        sb = (ds_bytes / 1024.0) / dt
        rp = dr_pkts / dt
        rb = (dr_bytes / 1024.0) / dt

        self._send_rate = f"{sp:.1f} pkt/s, {sb:.1f} KB/s"
        self._recv_rate = f"{rp:.1f} pkt/s, {rb:.1f} KB/s"
        self._send_total = f"{sent_pkts} pkts, {sent_bytes/1024.0:.1f} KB"
        self._recv_total = f"{recv_pkts} pkts, {recv_bytes/1024.0:.1f} KB"

        self.stats_lbl.configure(text=f"TX {self._send_rate} | RX {self._recv_rate}")
        self._update_status()

        self._last_stats_t = t
        self._last_sent_pkts = sent_pkts
        self._last_sent_bytes = sent_bytes
        self._last_recv_pkts = recv_pkts
        self._last_recv_bytes = recv_bytes

    # --------------------------
    # Paint actions: drawing primitives
    # --------------------------
    def _current_width(self) -> int:
        tool = self.tool_var.get()
        w = int(self.width_var.get())
        if tool == self.TOOL_PENCIL:
            return clamp_int(w, 1, 6)
        if tool == self.TOOL_BRUSH:
            return clamp_int(w, 3, 50)
        if tool == self.TOOL_ERASER:
            return clamp_int(w, 6, 80)
        return clamp_int(w, 1, 50)

    def _button_color(self, button: int) -> str:
        return self.primary_var.get() if button == 1 else self.secondary_var.get()

    def _tool_color(self, button: int) -> Tuple[str, Optional[str]]:
        """
        Returns (outline_color, fill_color or None)
        For eraser/freehand erase: outline_color becomes bg.
        For shapes: fill uses Secondary by default (when Fill shapes ON).
        Right-click swaps the outline color (paint-like), and swaps fill color as well.
        """
        tool = self.tool_var.get()
        if tool == self.TOOL_ERASER:
            return self.cfg.bg, None

        outline = self._button_color(button)

        if not self.fill_var.get():
            return outline, None

        # Paint-like: fill uses the "other" color
        if button == 1:
            fill = self.secondary_var.get()
        else:
            fill = self.primary_var.get()
        return outline, fill

    def _draw_segment(self, x0: int, y0: int, x1: int, y1: int, color: str, width: int) -> int:
        return self.canvas.create_line(
            x0, y0, x1, y1,
            fill=color,
            width=width,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
            smooth=False,
        )

    def _draw_polyline(self, pts_px: List[Tuple[int, int]], color: str, width: int, smooth: bool) -> int:
        flat: List[int] = []
        for x, y in pts_px:
            flat.extend([x, y])
        return self.canvas.create_line(
            *flat,
            fill=color,
            width=width,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
            smooth=bool(smooth),
            splinesteps=24,
        )

    def _draw_shape_item(self, shape: str, x0: int, y0: int, x1: int, y1: int,
                         outline: str, width: int, fill: Optional[str]) -> int:
        if shape == "line":
            return self.canvas.create_line(
                x0, y0, x1, y1,
                fill=outline, width=width, capstyle=tk.ROUND, joinstyle=tk.ROUND
            )
        if shape == "rect":
            return self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline=outline, width=width, fill=fill if fill else ""
            )
        if shape == "oval":
            return self.canvas.create_oval(
                x0, y0, x1, y1,
                outline=outline, width=width, fill=fill if fill else ""
            )
        # fallback
        return self.canvas.create_line(
            x0, y0, x1, y1, fill=outline, width=width
        )

    # --------------------------
    # Mouse events
    # --------------------------
    def _on_press(self, event, button: int):
        self._active_mouse_button = button
        tool = self.tool_var.get()

        # Picker
        if tool == self.TOOL_PICKER:
            self._pick_color_at(event.x, event.y, button=button)
            return

        # Bucket Fill
        if tool == self.TOOL_BUCKET:
            self._bucket_fill_at(event.x, event.y, button=button)
            return

        # Text
        if tool == self.TOOL_TEXT:
            self._text_popup(event.x, event.y, button=button)
            return

        # Freehand tools
        if tool in (self.TOOL_PENCIL, self.TOOL_BRUSH, self.TOOL_ERASER):
            self.local_stroke_id = str(uuid.uuid4())
            self.local_points = [self._norm(event.x, event.y)]
            self.local_last_px = (event.x, event.y)
            self.local_seq = 0
            self.local_temp_items = []
            return

        # Shapes
        if tool in (self.TOOL_LINE, self.TOOL_RECT, self.TOOL_OVAL):
            self.shape_start_px = (event.x, event.y)
            self._delete_shape_preview()
            # create preview
            outline, fill = self._tool_color(button)
            width = self._current_width()
            shape = "line" if tool == self.TOOL_LINE else ("rect" if tool == self.TOOL_RECT else "oval")
            self.shape_preview_item = self._draw_shape_item(shape, event.x, event.y, event.x, event.y, outline, width, fill)
            return

    def _on_move(self, event, button: int):
        tool = self.tool_var.get()

        # Freehand
        if tool in (self.TOOL_PENCIL, self.TOOL_BRUSH, self.TOOL_ERASER):
            if not self.local_stroke_id or not self.local_last_px:
                return

            x0, y0 = self.local_last_px
            x1, y1 = event.x, event.y

            dist = math.hypot(x1 - x0, y1 - y0)
            if dist < float(self.cfg.min_step_px):
                return

            width = self._current_width()
            outline, _ = self._tool_color(button)
            eraser = (tool == self.TOOL_ERASER)

            # local draw temp segment
            it = self._draw_segment(x0, y0, x1, y1, outline, width)
            self.local_temp_items.append(it)

            p0n = self._norm(x0, y0)
            p1n = self._norm(x1, y1)

            self._tick_lamport()
            seg_msg = {
                "v": self.MSG_VERSION,
                "type": "seg",
                "mid": self._new_mid(),
                "id": self.client_id,
                "user": self.cfg.username,
                "ts": now_ms(),
                "lc": self.lamport,
                "stroke": self.local_stroke_id,
                "seq": self.local_seq,
                "p0": p0n,
                "p1": p1n,
                "color": self._button_color(button) if not eraser else self.cfg.bg,
                "width": int(width),
                "eraser": bool(eraser),
            }
            self._broadcast_obj(seg_msg)

            self.local_points.append(p1n)
            self.local_last_px = (x1, y1)
            self.local_seq += 1
            return

        # Shapes preview
        if tool in (self.TOOL_LINE, self.TOOL_RECT, self.TOOL_OVAL):
            if not self.shape_start_px:
                return
            x0, y0 = self.shape_start_px
            x1, y1 = event.x, event.y
            outline, fill = self._tool_color(button)
            width = self._current_width()
            shape = "line" if tool == self.TOOL_LINE else ("rect" if tool == self.TOOL_RECT else "oval")
            self._delete_shape_preview()
            self.shape_preview_item = self._draw_shape_item(shape, x0, y0, x1, y1, outline, width, fill)
            return

    def _on_release(self, event, button: int):
        tool = self.tool_var.get()

        # Freehand finalize
        if tool in (self.TOOL_PENCIL, self.TOOL_BRUSH, self.TOOL_ERASER):
            if not self.local_stroke_id:
                return

            # add final point
            self.local_points.append(self._norm(event.x, event.y))

            pts = downsample_points(self.local_points, self.cfg.max_stroke_points)

            width = self._current_width()
            eraser = (tool == self.TOOL_ERASER)
            color = self.cfg.bg if eraser else self._button_color(button)

            op_id = self.local_stroke_id  # use stroke_id as op_id (keeps original behavior)
            self._tick_lamport()
            stroke_msg = {
                "v": self.MSG_VERSION,
                "type": "stroke",
                "mid": self._new_mid(),
                "id": self.client_id,
                "user": self.cfg.username,
                "ts": now_ms(),
                "lc": self.lamport,
                "op": op_id,
                "stroke": self.local_stroke_id,
                "pts": pts,
                "color": color,
                "width": int(width),
                "eraser": bool(eraser),
                "smooth": bool(self.smooth_var.get()),
            }

            # avoid giant packets
            raw = json.dumps(stroke_msg, separators=(",", ":")).encode("utf-8", errors="ignore")
            if len(raw) > self.cfg.max_packet_bytes and len(pts) > 10:
                shrink = len(pts)
                while len(raw) > self.cfg.max_packet_bytes and shrink > 10:
                    shrink = max(10, shrink // 2)
                    pts2 = downsample_points(pts, shrink)
                    stroke_msg["pts"] = pts2
                    raw = json.dumps(stroke_msg, separators=(",", ":")).encode("utf-8", errors="ignore")

            # locally replace temp segments with smooth polyline (like receiver)
            for it in self.local_temp_items:
                try:
                    self.canvas.delete(it)
                except Exception:
                    pass
            self.local_temp_items = []

            # Apply locally as a new op (this also clears redo globally)
            self._apply_op_message(stroke_msg, local_origin=True, is_redo=False)

            self._broadcast_obj(stroke_msg)
            self._log_event("TX", stroke_msg)

            # reset local stroke
            self.local_stroke_id = None
            self.local_points = []
            self.local_last_px = None
            self.local_seq = 0
            return

        # Shapes finalize
        if tool in (self.TOOL_LINE, self.TOOL_RECT, self.TOOL_OVAL):
            if not self.shape_start_px:
                return
            x0, y0 = self.shape_start_px
            x1, y1 = event.x, event.y
            self.shape_start_px = None
            self._delete_shape_preview()

            outline, fill = self._tool_color(button)
            width = self._current_width()
            shape = "line" if tool == self.TOOL_LINE else ("rect" if tool == self.TOOL_RECT else "oval")

            op_id = str(uuid.uuid4())

            self._tick_lamport()
            shape_msg = {
                "v": self.MSG_VERSION,
                "type": "shape",
                "mid": self._new_mid(),
                "id": self.client_id,
                "user": self.cfg.username,
                "ts": now_ms(),
                "lc": self.lamport,
                "op": op_id,
                "shape": shape,
                "p0": self._norm(x0, y0),
                "p1": self._norm(x1, y1),
                "outline": outline,
                "width": int(width),
                "fill": bool(fill is not None),
                "fill_color": fill if fill else "",
            }

            # local apply
            self._apply_op_message(shape_msg, local_origin=True, is_redo=False)

            self._broadcast_obj(shape_msg)
            self._log_event("TX", shape_msg)
            return

    def _delete_shape_preview(self):
        if self.shape_preview_item is not None:
            try:
                self.canvas.delete(self.shape_preview_item)
            except Exception:
                pass
        self.shape_preview_item = None

    # --------------------------
    # Picker, Text, Bucket
    # --------------------------
    def _pick_color_at(self, x: int, y: int, button: int):
        items = self.canvas.find_overlapping(x-1, y-1, x+1, y+1)
        if not items:
            return
        item = items[-1]
        # try fill then outline
        c = self.canvas.itemcget(item, "fill")
        if not c:
            c = self.canvas.itemcget(item, "outline")
        if c:
            if button == 1:
                self._set_primary(c)
            else:
                self._set_secondary(c)

    def _text_popup(self, x: int, y: int, button: int):
        top = tk.Toplevel(self.root)
        top.title("Text")
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()

        ttk.Label(top, text="Enter text:").pack(padx=10, pady=(10, 4), anchor=tk.W)
        ent = ttk.Entry(top, width=40)
        ent.pack(padx=10, pady=(0, 10))
        ent.focus_set()

        btn_row = ttk.Frame(top)
        btn_row.pack(padx=10, pady=(0, 10), fill=tk.X)

        def ok():
            text = ent.get().strip()
            top.destroy()
            if text:
                self._place_text_broadcast(x, y, text, button=button)

        def cancel():
            top.destroy()

        ttk.Button(btn_row, text="OK", command=ok).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=(6, 0))

        top.bind("<Return>", lambda e: ok())
        top.bind("<Escape>", lambda e: cancel())

    def _place_text_broadcast(self, x: int, y: int, text: str, button: int):
        op_id = str(uuid.uuid4())
        color = self._button_color(button)
        size = int(self.text_size_var.get())

        self._tick_lamport()
        msg = {
            "v": self.MSG_VERSION,
            "type": "text",
            "mid": self._new_mid(),
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "lc": self.lamport,
            "op": op_id,
            "pos": self._norm(x, y),
            "text": text,
            "color": color,
            "size": size,
        }

        # local apply
        self._apply_op_message(msg, local_origin=True, is_redo=False)

        self._broadcast_obj(msg)
        self._log_event("TX", msg)

    def _bucket_fill_at(self, x: int, y: int, button: int):
        """
        Paint-like bucket for vector shapes:
        - If clicking inside a shape item (rect/oval/polygon): fill that item only (undoable, broadcast)
        - Otherwise fill background (undoable, broadcast)
        """
        fill_color = self._button_color(button)

        # Find top-most fillable shape under cursor
        items = self.canvas.find_overlapping(x, y, x, y)
        target_item: Optional[int] = None
        for it in reversed(items):
            t = ""
            try:
                t = self.canvas.type(it)
            except Exception:
                t = ""
            if t in ("rectangle", "oval", "polygon"):
                target_item = it
                break

        if target_item is None:
            # fall back to background fill
            self._set_bg_broadcast(fill_color)
            return

        # Identify owning op (so remote peers can find the same item)
        target_op = self.item_to_op.get(target_item, "")
        if not target_op:
            # If it isn't associated (e.g., legacy item), fill locally only
            try:
                self.canvas.itemconfigure(target_item, fill=fill_color)
            except Exception:
                pass
            self._update_status()
            return

        prev_fill = ""
        try:
            prev_fill = self.canvas.itemcget(target_item, "fill") or ""
        except Exception:
            prev_fill = ""

        # If no change, do nothing
        if (prev_fill or "") == (fill_color or ""):
            return

        op_id = str(uuid.uuid4())
        self._tick_lamport()
        msg = {
            "v": self.MSG_VERSION,
            "type": "fill",
            "mid": self._new_mid(),
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "lc": self.lamport,
            "op": op_id,
            "target": target_op,
            "color": fill_color,
            "prev": prev_fill,
        }

        # local apply
        self._apply_op_message(msg, local_origin=True, is_redo=False)

        self._broadcast_obj(msg)
        self._log_event("TX", msg)

    # --------------------------
    # Background & Clear/Save
    # --------------------------
    def _set_bg_broadcast(self, bg: str):
        prev = self.cfg.bg
        if (prev or "") == (bg or ""):
            return

        op_id = str(uuid.uuid4())
        self._tick_lamport()
        msg = {
            "v": self.MSG_VERSION,
            "type": "bg",
            "mid": self._new_mid(),
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "lc": self.lamport,
            "op": op_id,
            "bg": bg,
            "prev": prev,
        }

        # local apply (undoable now)
        self._apply_op_message(msg, local_origin=True, is_redo=False)

        self._broadcast_obj(msg)
        self._log_event("TX", msg)

    def _new_local(self):
        if not messagebox.askyesno("New", "Clear your local canvas (only local)?"):
            return
        self._clear_local_only()

    def _clear_local_only(self):
        self.canvas.delete("all")
        self.ops.clear()
        self.item_to_op.clear()
        self.pending_undo.clear()
        self.pending_redo.clear()
        self.remote_temp_items.clear()
        self.remote_final.clear()

        # Reset background to configured default (local only)
        try:
            self.canvas.configure(background=self.cfg.bg)
        except Exception:
            pass

        self._update_status()
        self._log_event("LOCAL", {"type": "new", "user": self.cfg.username, "ts": now_ms(), "op": ""})

    def _clear_broadcast(self):
        if not messagebox.askyesno("Clear Canvas", "Clear canvas for ALL users (broadcast)?"):
            return
        self._clear_local_only()

        self._tick_lamport()
        msg = {
            "v": self.MSG_VERSION,
            "type": "clear",
            "mid": self._new_mid(),
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "lc": self.lamport,
        }
        self._broadcast_obj(msg)
        self._log_event("TX", msg)

    def _save_postscript(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".ps",
            filetypes=[("PostScript", "*.ps")],
            title="Save Canvas as .ps"
        )
        if not filename:
            return
        try:
            ps = self.canvas.postscript(colormode="color")
            with open(filename, "w", encoding="utf-8", errors="ignore") as f:
                f.write(ps)
            messagebox.showinfo("Saved", f"Saved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    # --------------------------
    # Shared Undo/Redo (broadcast)
    # --------------------------
    def _pick_last_active_op(self) -> Optional[str]:
        """
        Deterministic-ish: choose active op with max created_key.
        """
        best: Optional[Tuple[Tuple[int, str, str], str]] = None
        for op_id, rec in self.ops.items():
            if not rec.get("active"):
                continue
            ck = rec.get("created_key")
            if not (isinstance(ck, tuple) and len(ck) == 3):
                continue
            if best is None or ck > best[0]:
                best = (ck, op_id)
        return best[1] if best else None

    def _pick_last_undone_op(self) -> Optional[str]:
        """
        Deterministic: choose inactive op with undone_key max.
        """
        best: Optional[Tuple[Tuple[int, str, str], str]] = None
        for op_id, rec in self.ops.items():
            uk = rec.get("undone_key")
            if rec.get("active"):
                continue
            if not (isinstance(uk, tuple) and len(uk) == 3):
                continue
            if best is None or uk > best[0]:
                best = (uk, op_id)
        return best[1] if best else None

    def _undo_shared(self):
        op_id = self._pick_last_active_op()
        if not op_id:
            return

        self._tick_lamport()
        mid = self._new_mid()
        msg = {
            "v": self.MSG_VERSION,
            "type": "undo",
            "mid": mid,
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "lc": self.lamport,
            "target": op_id,
        }

        # apply locally
        self._apply_undo_command(msg, local_initiator=True)

        # broadcast
        self._broadcast_obj(msg)
        self._log_event("TX", msg)

    def _redo_shared(self):
        op_id = self._pick_last_undone_op()
        if not op_id:
            return

        payload = None
        rec = self.ops.get(op_id)
        if rec and isinstance(rec.get("msg"), dict):
            payload = dict(rec["msg"])

        self._tick_lamport()
        mid = self._new_mid()
        msg = {
            "v": self.MSG_VERSION,
            "type": "redo",
            "mid": mid,
            "id": self.client_id,
            "user": self.cfg.username,
            "ts": now_ms(),
            "lc": self.lamport,
            "target": op_id,
            "payload": payload or {},
        }

        # apply locally
        self._apply_redo_command(msg, local_initiator=True)

        # broadcast
        self._broadcast_obj(msg)
        self._log_event("TX", msg)

    def _apply_undo_command(self, msg: Dict[str, Any], local_initiator: bool):
        op_id = msg.get("target") or msg.get("op")
        if not isinstance(op_id, str) or not op_id:
            return
        cmd_key = self._cmd_key_from_msg(msg)

        rec = self.ops.get(op_id)
        if not rec:
            # op not received yet; defer
            self.pending_undo[op_id] = cmd_key
            return

        if not rec.get("active"):
            # already undone (idempotent)
            return

        self._undo_op_inplace(op_id, cmd_key)

    def _apply_redo_command(self, msg: Dict[str, Any], local_initiator: bool):
        op_id = msg.get("target") or msg.get("op")
        if not isinstance(op_id, str) or not op_id:
            return

        payload = msg.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        rec = self.ops.get(op_id)
        if rec and rec.get("active"):
            return  # already active

        if not rec:
            # We don't know this op yet; try payload now, else defer
            if payload.get("op") == op_id and payload.get("type") in ("stroke", "shape", "text", "fill", "bg"):
                self._apply_op_message(payload, local_origin=False, is_redo=True)
                rec2 = self.ops.get(op_id)
                if rec2:
                    rec2["undone_key"] = None
                return
            self.pending_redo[op_id] = payload
            return

        # We have the op but it's inactive: re-apply from stored msg
        stored = rec.get("msg")
        if isinstance(stored, dict):
            # Re-apply create/mutate without changing op_id
            self._apply_op_message(stored, local_origin=False, is_redo=True)
            rec2 = self.ops.get(op_id)
            if rec2:
                rec2["undone_key"] = None

    def _undo_op_inplace(self, op_id: str, cmd_key: Tuple[int, str, str]):
        rec = self.ops.get(op_id)
        if not rec:
            return

        kind = rec.get("kind", "create")

        if kind == "create":
            # delete items
            for it in rec.get("items", []) or []:
                try:
                    self.canvas.delete(it)
                except Exception:
                    pass
                try:
                    self.item_to_op.pop(int(it), None)
                except Exception:
                    pass
            rec["items"] = []
            rec["active"] = False
            rec["undone_key"] = cmd_key

        elif kind == "fill":
            # revert fill of target shape item
            target_op = str(rec.get("meta", {}).get("target", ""))
            prev_fill = str(rec.get("meta", {}).get("prev", ""))
            self._set_target_shape_fill(target_op, prev_fill)
            rec["active"] = False
            rec["undone_key"] = cmd_key

        elif kind == "bg":
            prev_bg = str(rec.get("meta", {}).get("prev", self.cfg.bg))
            self.cfg.bg = prev_bg
            self.canvas.configure(background=prev_bg)
            rec["active"] = False
            rec["undone_key"] = cmd_key

        self._update_status()

    # --------------------------
    # Network receive loop (thread)
    # --------------------------
    def _recv_loop(self):
        while not self.stop_evt.is_set():
            got = self.transport.recv_once()
            if not got:
                continue
            obj, addr = got
            self.net_queue.put((obj, addr))

    def _schedule_queue_pump(self):
        self._pump_queue()
        self.root.after(12, self._schedule_queue_pump)  # ~80fps

    def _pump_queue(self):
        for _ in range(400):
            try:
                obj, addr = self.net_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_message(obj, addr)
            except Exception:
                if self.cfg.debug:
                    print("[GUI] error handling message:", obj)

    # --------------------------
    # Message handling
    # --------------------------
    def _handle_message(self, obj: Dict[str, Any], addr: Tuple[str, int]):
        if not isinstance(obj, dict):
            return
        if obj.get("v") != self.MSG_VERSION:
            return

        mid = obj.get("mid")
        if self._seen(mid):
            return

        mtype = obj.get("type")
        sender_id = obj.get("id")
        sender_user = obj.get("user", "?")

        # Lamport update
        try:
            lc = int(obj.get("lc", 0))
        except Exception:
            lc = 0
        self._tick_lamport(remote_lc=lc)

        # Ignore our own packets (unless loopback enabled; then ignore anyway to avoid double)
        if sender_id == self.client_id:
            return

        # update peer tracking
        if isinstance(sender_id, str):
            self.peers[sender_id] = {
                "user": str(sender_user),
                "last": now_ms(),
                "ip": addr[0],
                "port": int(obj.get("port", self.cfg.port)),
            }
            self._update_peer_list_ui()

        self.last_rx = f"{sender_user} @ {addr[0]}:{addr[1]} ({mtype})"
        self.peer_details.configure(text=f"Last RX: {self.last_rx}")

        # Log selected message types
        if mtype not in ("seg", "hello"):
            self._log_event("RX", obj, addr=addr)

        if mtype == "hello":
            self._update_status()
            return
        if mtype == "bye":
            if isinstance(sender_id, str):
                self.peers.pop(sender_id, None)
            self._update_peer_list_ui()
            self._update_status()
            return

        if mtype == "clear":
            self._clear_local_only()
            self._update_status()
            return

        if mtype == "undo":
            self._apply_undo_command(obj, local_initiator=False)
            return

        if mtype == "redo":
            self._apply_redo_command(obj, local_initiator=False)
            return

        # drawing messages
        if mtype == "seg":
            self._handle_seg(obj)
            return

        if mtype in ("stroke", "shape", "text", "fill", "bg"):
            self._apply_op_message(obj, local_origin=False, is_redo=False)
            return

    def _handle_seg(self, obj: Dict[str, Any]):
        stroke_id = obj.get("stroke")
        if not isinstance(stroke_id, str):
            return

        # ignore late segments after final stroke applied
        if stroke_id in self.remote_final:
            return

        p0 = obj.get("p0")
        p1 = obj.get("p1")
        if not (isinstance(p0, list) and isinstance(p1, list) and len(p0) == 2 and len(p1) == 2):
            return

        color = str(obj.get("color", "#000000"))
        width = int(obj.get("width", 3))
        eraser = bool(obj.get("eraser", False))
        if eraser:
            color = self.cfg.bg

        x0, y0 = self._denorm(p0)
        x1, y1 = self._denorm(p1)
        it = self._draw_segment(x0, y0, x1, y1, color, width)
        self.remote_temp_items.setdefault(stroke_id, []).append(it)

    # --------------------------
    # Applying operations
    # --------------------------
    def _clear_redo_chain_if_any(self):
        """
        Paint behavior: any new operation clears redo history.
        We implement this by removing undone_key markers from any inactive ops.
        """
        changed = False
        for rec in self.ops.values():
            if not rec.get("active") and rec.get("undone_key") is not None:
                rec["undone_key"] = None
                changed = True
        if changed:
            self._update_status()

    def _apply_op_message(self, obj: Dict[str, Any], local_origin: bool, is_redo: bool):
        mtype = obj.get("type")
        op_id = obj.get("op")
        if not isinstance(op_id, str) or not op_id:
            return
        if mtype not in ("stroke", "shape", "text", "fill", "bg"):
            return

        # If op exists and active, ignore duplicates.
        existing = self.ops.get(op_id)
        if existing and existing.get("active"):
            return

        # New operation clears redo history (unless this apply is part of redo)
        if not is_redo:
            self._clear_redo_chain_if_any()

        items: List[int] = []
        kind = "create"
        meta: Dict[str, Any] = {}

        if mtype == "stroke":
            items = self._apply_stroke(obj)
            kind = "create"
        elif mtype == "shape":
            items = self._apply_shape(obj)
            kind = "create"
        elif mtype == "text":
            items = self._apply_text(obj)
            kind = "create"
        elif mtype == "fill":
            kind = "fill"
            meta = self._apply_fill(obj)
            items = meta.get("items", [])
        elif mtype == "bg":
            kind = "bg"
            meta = self._apply_bg(obj)
            items = []

        created_key = self._created_key_from_msg(obj)

        if op_id not in self.ops:
            self.ops[op_id] = {
                "msg": dict(obj),
                "items": items,
                "active": True,
                "kind": kind,
                "created_key": created_key,
                "undone_key": None,
                "meta": meta,
            }
        else:
            # op exists but inactive; reapply (redo) path
            rec = self.ops[op_id]
            rec["msg"] = dict(obj)
            rec["items"] = items
            rec["active"] = True
            rec["kind"] = kind
            rec["created_key"] = rec.get("created_key", created_key)
            rec["meta"] = meta
            rec["undone_key"] = None

        # map items to op (helps bucket)
        for it in items:
            try:
                self.item_to_op[int(it)] = op_id
            except Exception:
                pass

        # If we had a pending undo command for this op, apply it now
        if op_id in self.pending_undo:
            cmd_key = self.pending_undo.pop(op_id)
            self._undo_op_inplace(op_id, cmd_key)

        # If we had a pending redo for an op we didn't know earlier, and now we know it, apply
        if op_id in self.pending_redo and not self.ops.get(op_id, {}).get("active"):
            payload = self.pending_redo.pop(op_id)
            if isinstance(payload, dict) and payload.get("op") == op_id:
                self._apply_op_message(payload, local_origin=False, is_redo=True)

        self._update_status()

    def _apply_stroke(self, obj: Dict[str, Any]) -> List[int]:
        stroke_id = obj.get("stroke")
        pts = obj.get("pts")
        if not (isinstance(stroke_id, str) and isinstance(pts, list) and len(pts) >= 2):
            return []

        # remove temp segments for this stroke if any
        old = self.remote_temp_items.pop(stroke_id, [])
        for it in old:
            try:
                self.canvas.delete(it)
            except Exception:
                pass

        color = str(obj.get("color", "#000000"))
        width = int(obj.get("width", 3))
        eraser = bool(obj.get("eraser", False))
        smooth = bool(obj.get("smooth", True))
        if eraser:
            color = self.cfg.bg

        pts_px = [self._denorm(p) for p in pts if isinstance(p, list) and len(p) == 2]
        if len(pts_px) < 2:
            return []

        poly_id = self._draw_polyline(pts_px, color, width, smooth)
        self.remote_final[stroke_id] = now_ms()
        return [poly_id]

    def _apply_shape(self, obj: Dict[str, Any]) -> List[int]:
        shape = obj.get("shape")
        p0 = obj.get("p0")
        p1 = obj.get("p1")
        if not (isinstance(shape, str) and isinstance(p0, list) and isinstance(p1, list) and len(p0) == 2 and len(p1) == 2):
            return []

        outline = str(obj.get("outline", "#000000"))
        width = int(obj.get("width", 3))
        fill = bool(obj.get("fill", False))
        fill_color = str(obj.get("fill_color", "")) if fill else ""

        x0, y0 = self._denorm(p0)
        x1, y1 = self._denorm(p1)
        item = self._draw_shape_item(shape, x0, y0, x1, y1, outline, width, fill_color if fill else None)
        return [item]

    def _apply_text(self, obj: Dict[str, Any]) -> List[int]:
        pos = obj.get("pos")
        text = obj.get("text")
        color = obj.get("color")
        size = obj.get("size")
        if not (isinstance(pos, list) and len(pos) == 2 and isinstance(text, str) and isinstance(color, str)):
            return []
        try:
            sz = int(size)
        except Exception:
            sz = 14
        x, y = self._denorm(pos)
        item = self.canvas.create_text(x, y, text=text, fill=color, anchor=tk.NW, font=("Segoe UI", sz))
        return [item]

    def _set_target_shape_fill(self, target_op: str, fill_color: str):
        rec = self.ops.get(target_op)
        if not rec or not rec.get("active"):
            return
        # Shape is expected to have 1 item
        items = rec.get("items", []) or []
        if not items:
            return
        it = items[0]
        try:
            t = self.canvas.type(it)
        except Exception:
            t = ""
        if t not in ("rectangle", "oval", "polygon"):
            return
        try:
            self.canvas.itemconfigure(it, fill=fill_color or "")
        except Exception:
            pass

    def _apply_fill(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        target = obj.get("target")
        color = obj.get("color")
        prev = obj.get("prev", "")
        if not (isinstance(target, str) and isinstance(color, str)):
            return {"items": [], "target": "", "color": "", "prev": ""}

        # Apply fill now
        self._set_target_shape_fill(target, color)

        # Include the target's current item id (if any) to show in history and allow mapping
        items: List[int] = []
        trec = self.ops.get(target)
        if trec and trec.get("active"):
            items = list(trec.get("items", []) or [])

        return {"items": items, "target": target, "color": color, "prev": str(prev or "")}

    def _apply_bg(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        bg = obj.get("bg")
        prev = obj.get("prev", self.cfg.bg)
        if not isinstance(bg, str):
            return {"prev": self.cfg.bg, "bg": self.cfg.bg}

        # Apply background
        self.cfg.bg = bg
        try:
            self.canvas.configure(background=bg)
        except Exception:
            pass
        return {"prev": str(prev or ""), "bg": bg}

    # --------------------------
    # Closing
    # --------------------------
    def _on_close(self):
        if self.stop_evt.is_set():
            return
        self.stop_evt.set()

        try:
            self._send_bye()
        except Exception:
            pass

        if self.igmp:
            try:
                self.igmp.stop()
            except Exception:
                pass

        try:
            self.transport.close()
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# =========================
# CLI / Main
# =========================

def list_ifaces():
    print("\n=== Interface helper ===")
    print("OS hostname:", socket.gethostname())
    guessed = guess_local_ip()
    print("Guessed primary IPv4:", guessed)

    if SCAPY_OK:
        print("\nScapy interfaces:")
        try:
            for n in scapy_get_if_list():
                ip = ""
                try:
                    ip = scapy_get_if_addr(n)
                except Exception:
                    ip = ""
                print(f"  - {n}   ip={ip}")
        except Exception as e:
            print("  (failed to list scapy interfaces)", e)
    else:
        print("\nScapy not available. (Install scapy if you want interface listing + IGMP crafting.)")

    print("\nTip:")
    print("  Use --ifaddr YOUR_VM_IP (e.g., 10.0.2.10) so multicast joins the correct adapter.")
    print("  If using --igmp, also use --scapy-iface with the interface name (if auto-match fails).")
    print("")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Shared Paint over UDP Multicast (single program, shared undo/redo).")

    ap.add_argument("--list-ifaces", action="store_true", help="List interfaces (best with scapy installed) and exit.")

    ap.add_argument("--group", default="239.1.1.1", help="Multicast group (default: 239.1.1.1)")
    ap.add_argument("--port", default=5000, type=int, help="UDP port (default: 5000)")
    ap.add_argument("--ttl", default=16, type=int, help="Multicast TTL (>=2 to cross router) (default: 16)")
    ap.add_argument("--ifaddr", default=None, help="Local interface IPv4 to use (recommended), e.g. 10.0.2.10")

    ap.add_argument("--user", default=None, help="Username shown in app (default: OS username/hostname)")
    ap.add_argument("--bg", default="white", help="Canvas background color (default: white)")
    ap.add_argument("--primary", default="#0b65c2", help="Primary color (default: #0b65c2)")
    ap.add_argument("--secondary", default="#ff0000", help="Secondary color (default: #ff0000)")

    ap.add_argument("--pen-width", default=3, type=int, help="Initial pencil width (default: 3)")
    ap.add_argument("--brush-width", default=10, type=int, help="Default brush width (default: 10)")
    ap.add_argument("--eraser-width", default=18, type=int, help="Default eraser width (default: 18)")
    ap.add_argument("--text-size", default=18, type=int, help="Text size (default: 18)")

    ap.add_argument("--min-step", default=2, type=int, help="Minimum mouse movement (px) to send a segment (default: 2)")
    ap.add_argument("--max-stroke-points", default=80, type=int, help="Max points in final stroke packet (default: 80)")
    ap.add_argument("--max-packet-bytes", default=1300, type=int, help="Try to keep stroke packets under this size (default: 1300)")
    ap.add_argument("--presence-interval", default=5, type=int, help="Seconds between HELLO packets (default: 5)")
    ap.add_argument("--stats-interval", default=500, type=int, help="Stats refresh in ms (default: 500)")

    ap.add_argument("--peer-unicast", action="store_true",
                    help="Send multicast AND unicast to known peers (fixes one-way IGMP-proxy setups).")
    ap.add_argument("--loopback", action="store_true", help="Receive your own multicast (debug).")

    # IGMP via scapy (optional)
    ap.add_argument("--igmp", action="store_true", help="Enable Scapy IGMPv2 JOIN keepalive + LEAVE on exit (optional).")
    ap.add_argument("--igmp-interval", default=10, type=int, help="Seconds between IGMP JOIN keepalives (default: 10)")
    ap.add_argument("--scapy-iface", default=None, help="Scapy interface name/substring (use if auto-match fails).")

    ap.add_argument("--debug", action="store_true", help="Verbose debugging prints.")
    return ap


def main():
    _try_import_scapy()

    ap = build_arg_parser()
    args = ap.parse_args()

    if args.list_ifaces:
        list_ifaces()
        return

    ifaddr = args.ifaddr or guess_local_ip()
    if not ifaddr:
        raise SystemExit(
            "Could not auto-detect ifaddr. Please run with:\n"
            "  py mcast_canvas_paint.py --ifaddr YOUR_VM_IP\n"
            "Example:\n"
            "  py mcast_canvas_paint.py --ifaddr 10.0.2.10\n"
        )
    if ifaddr.startswith("127."):
        raise SystemExit("Detected loopback IP. Please pass --ifaddr (e.g., 10.0.2.10).")

    username = args.user or os.environ.get("USERNAME") or os.environ.get("USER") or socket.gethostname()

    cfg = AppConfig(
        group=str(args.group),
        port=int(args.port),
        ttl=int(args.ttl),
        ifaddr=str(ifaddr),
        username=str(username),

        bg=str(args.bg),
        primary_color=str(args.primary),
        secondary_color=str(args.secondary),
        pen_width=int(args.pen_width),
        brush_width=int(args.brush_width),
        eraser_width=int(args.eraser_width),
        text_size=int(args.text_size),

        min_step_px=int(args.min_step),
        max_stroke_points=int(args.max_stroke_points),
        max_packet_bytes=int(args.max_packet_bytes),
        presence_interval_s=int(args.presence_interval),
        stats_interval_ms=int(args.stats_interval),

        peer_unicast=bool(args.peer_unicast),
        loopback=bool(args.loopback),
        igmp_enable=bool(args.igmp),
        igmp_interval_s=int(args.igmp_interval),
        scapy_iface=args.scapy_iface,
        debug=bool(args.debug),
    )

    if cfg.igmp_enable:
        if not SCAPY_OK:
            raise SystemExit(
                "You used --igmp but Scapy is not available.\n"
                "Fix:\n"
                "  py -m pip install --upgrade scapy\n"
                "Also install Npcap on Windows.\n"
            )
        if IGMP is None:
            raise SystemExit(
                "Scapy installed but IGMP layer not found.\n"
                "Fix:\n"
                "  py -m pip install --upgrade scapy\n"
            )

    app = MulticastPaintApp(cfg)
    app.run()


if __name__ == "__main__":
    main()
