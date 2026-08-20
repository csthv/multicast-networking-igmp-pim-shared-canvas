# -*- coding: utf-8 -*-
"""
receiver.py (run on PC2 and PC3 - downstream)

- Sends IGMPv2 JOIN immediately and every join_interval seconds.
- Sniffs IGMP + multicast TEXT + unicast PONG.
- On receiving multicast TEXT: sends unicast PING back to sender (ip.src).
- On Ctrl+C: sends IGMPv2 LEAVE.

Examples:
  py receiver.py --group 239.1.1.1 --port 5000 --join-interval 10
  py receiver.py --list-ifaces
  py receiver.py --iface "Ethernet"   (only if auto-pick is wrong)
"""

import argparse
import time
from ipaddress import IPv4Address

from scapy.all import (
    conf,
    Ether, IP, UDP, Raw,
    ARP,
    sendp, sniff, srp1,
    get_if_list, get_if_hwaddr, get_if_addr,
)

# ---- IGMP import compatibility ----
IGMP = None
try:
    from scapy.layers.inet import IGMP  # type: ignore
except Exception:
    try:
        from scapy.contrib.igmp import IGMP  # type: ignore
    except Exception:
        IGMP = None

try:
    from scapy.layers.inet import IPOption_Router_Alert  # type: ignore
except Exception:
    IPOption_Router_Alert = None

try:
    from scapy.arch.windows import get_windows_if_list
    WINDOWS = True
except Exception:
    WINDOWS = False

DEFAULT_GROUP = "239.1.1.1"
DEFAULT_PORT = 5000
DEFAULT_JOIN_INTERVAL = 10


def multicast_mac(ip_str):
    ip = int(IPv4Address(ip_str))
    mac = [0x01, 0x00, 0x5E, (ip >> 16) & 0x7F, (ip >> 8) & 0xFF, ip & 0xFF]
    return ":".join("{:02x}".format(b) for b in mac)


def list_ifaces():
    print("\nAvailable interfaces (Scapy):")
    for i, name in enumerate(get_if_list()):
        try:
            ip = get_if_addr(name)
        except Exception:
            ip = ""
        print("  [{:d}] {}   ip={}".format(i, name, ip))
    print("")


def pick_iface(user_iface, prefer_ip):
    if user_iface:
        key = user_iface.strip().lower()

        if WINDOWS:
            try:
                for it in get_windows_if_list():
                    desc = (it.get("description") or "").lower()
                    name = (it.get("name") or "").lower()
                    guid = (it.get("guid") or "").lower()
                    if key in desc or key in name or key in guid:
                        return it.get("name")
            except Exception:
                pass

        for n in get_if_list():
            nl = n.lower()
            if key == nl or key in nl:
                return n

        raise SystemExit("[RECEIVER] Could not match iface '{}'. Use --list-ifaces.".format(user_iface))

    if prefer_ip:
        for n in get_if_list():
            try:
                if get_if_addr(n) == prefer_ip:
                    return n
            except Exception:
                pass
        raise SystemExit("[RECEIVER] No interface has IPv4={}. Use --list-ifaces or --iface.".format(prefer_ip))

    for n in get_if_list():
        try:
            ip = get_if_addr(n)
            if ip and ip != "0.0.0.0" and ip != "127.0.0.1":
                return n
        except Exception:
            pass

    raise SystemExit("[RECEIVER] Could not auto-pick an interface. Use --list-ifaces and --iface.")


def ip_with_router_alert(src_ip, dst_ip, ttl):
    if IPOption_Router_Alert is not None:
        return IP(src=src_ip, dst=dst_ip, ttl=ttl, options=[IPOption_Router_Alert()])
    return IP(src=src_ip, dst=dst_ip, ttl=ttl)


def build_igmp_join(src_mac, src_ip, group):
    dst_mac = multicast_mac(group)
    return (
        Ether(src=src_mac, dst=dst_mac) /
        ip_with_router_alert(src_ip, group, ttl=1) /
        IGMP(type=0x16, gaddr=group)
    )


def build_igmp_leave(src_mac, src_ip, group):
    leave_dst = "224.0.0.2"
    dst_mac = multicast_mac(leave_dst)
    return (
        Ether(src=src_mac, dst=dst_mac) /
        ip_with_router_alert(src_ip, leave_dst, ttl=1) /
        IGMP(type=0x17, gaddr=group)
    )


def route_next_hop(dst_ip):
    try:
        r = conf.route.route(dst_ip)
        if isinstance(r, (list, tuple)) and len(r) >= 3:
            gw = r[2]
            if isinstance(gw, str) and gw and gw != "0.0.0.0":
                return gw
        return dst_ip
    except Exception:
        return dst_ip


def arp_resolve(iface, src_ip, src_mac, target_ip, timeout=1.0):
    try:
        req = Ether(src=src_mac, dst="ff:ff:ff:ff:ff:ff") / ARP(
            op=1, psrc=src_ip, hwsrc=src_mac, pdst=target_ip
        )
        ans = srp1(req, iface=iface, timeout=timeout, verbose=False)
        if ans and ans.haslayer(ARP):
            return ans[ARP].hwsrc
    except Exception:
        pass
    return None


def l2_dst_mac_for_unicast(iface, src_ip, src_mac, dst_ip, cache):
    nh = route_next_hop(dst_ip)
    if nh in cache:
        return cache[nh]
    mac = arp_resolve(iface, src_ip, src_mac, nh)
    if mac:
        cache[nh] = mac
    return mac


def extract_text(pkt):
    if pkt and pkt.haslayer(Raw):
        try:
            return bytes(pkt[Raw].load).decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""
    return ""


def main():
    conf.use_pcap = True
    conf.sniff_promisc = True
    try:
        conf.route.resync()
    except Exception:
        pass

    if IGMP is None:
        raise SystemExit(
            "[RECEIVER] Your Scapy build does not have IGMP support.\n"
            "Fix:\n"
            "  py -m pip install --upgrade scapy\n"
        )

    ap = argparse.ArgumentParser(description="Scapy receiver (auto iface): IGMP JOIN + send PING + recv PONG.")
    ap.add_argument("--list-ifaces", action="store_true", help="List interfaces and exit.")
    ap.add_argument("--iface", default=None, help="(Optional) Interface name/substring if auto-pick is wrong.")
    ap.add_argument("--src-ip", default=None, help="(Optional) Source IPv4 (default: interface IPv4).")
    ap.add_argument("--src-mac", default=None, help="(Optional) Spoof source MAC (default: interface MAC).")

    ap.add_argument("--group", default=DEFAULT_GROUP, help="Multicast group IP.")
    ap.add_argument("--port", default=DEFAULT_PORT, type=int, help="UDP port.")
    ap.add_argument("--join-interval", default=DEFAULT_JOIN_INTERVAL, type=int, help="Seconds between IGMP JOIN keepalives.")
    args = ap.parse_args()

    if args.list_ifaces:
        list_ifaces()
        return

    iface = pick_iface(args.iface, args.src_ip)

    src_ip = args.src_ip or get_if_addr(iface)
    if not src_ip or src_ip in ("0.0.0.0", "127.0.0.1"):
        raise SystemExit("[RECEIVER] Could not determine a valid src IP. Use --src-ip or --iface.")

    src_mac = args.src_mac or get_if_hwaddr(iface)

    # Capture:
    # - IGMP
    # - multicast UDP to group:port
    # - unicast UDP to me:port (PONG)
    bpf = "igmp or (udp and dst port {} and (dst host {} or dst host {}))".format(
        args.port, args.group, src_ip
    )

    print("[RECEIVER] iface={}".format(iface))
    print("[RECEIVER] src_ip={}  src_mac={}".format(src_ip, src_mac))
    print("[RECEIVER] group={}:{}  join_interval={}s".format(args.group, args.port, args.join_interval))
    print("[RECEIVER] BPF filter: {}".format(bpf))
    print("Press Ctrl+C to send LEAVE and stop.\n")

    mac_cache = {}

    def send_join():
        pkt = build_igmp_join(src_mac, src_ip, args.group)
        sendp(pkt, iface=iface, verbose=False)
        print("[RECEIVER] IGMPv2 JOIN sent: src={} group={}".format(src_ip, args.group))

    def send_leave():
        pkt = build_igmp_leave(src_mac, src_ip, args.group)
        sendp(pkt, iface=iface, verbose=False)
        print("[RECEIVER] IGMPv2 LEAVE sent: src={} group={} dst=224.0.0.2".format(src_ip, args.group))

    def send_ping(to_ip):
        dst_mac = l2_dst_mac_for_unicast(iface, src_ip, src_mac, to_ip, mac_cache)
        if not dst_mac:
            print("[RECEIVER] !!! ARP failed for next-hop toward {} (check gateway/ARP/firewall).".format(to_ip))
            return

        pkt = (
            Ether(src=src_mac, dst=dst_mac) /
            IP(src=src_ip, dst=to_ip, ttl=64) /
            UDP(sport=args.port, dport=args.port) /
            Raw(load=b"PING")
        )
        sendp(pkt, iface=iface, verbose=False)
        print("[RECEIVER] >>> Sent unicast PING to sender {}".format(to_ip))

    def handle(pkt):
        if not pkt or not pkt.haslayer(IP):
            return

        ip = pkt[IP]

        if pkt.haslayer(IGMP):
            ig = pkt[IGMP]
            gaddr = getattr(ig, "gaddr", "N/A")
            print("[RECEIVER][IGMP] type=0x{:02x} ip.src={} ip.dst={} gaddr={}".format(
                int(ig.type), ip.src, ip.dst, gaddr
            ))
            return

        if not pkt.haslayer(UDP):
            return

        udp = pkt[UDP]
        text = extract_text(pkt)

        # Multicast TEXT
        if ip.dst == args.group and int(udp.dport) == int(args.port):
            print("[RECEIVER][MCAST-UDP] {}:{} -> {}:{} | {!r}".format(ip.src, int(udp.sport), ip.dst, int(udp.dport), text))
            if text.upper() not in ("PING", "PONG"):
                send_ping(ip.src)
            return

        # Unicast PONG to me
        if ip.dst == src_ip and int(udp.dport) == int(args.port):
            if text.upper() == "PONG":
                print("[RECEIVER] <<< Received unicast PONG from sender {}".format(ip.src))
            else:
                print("[RECEIVER][UCAST-UDP] {}:{} -> {}:{} | {!r}".format(ip.src, int(udp.sport), ip.dst, int(udp.dport), text))

    send_join()
    next_join = time.time() + int(args.join_interval)

    try:
        while True:
            now = time.time()
            if now >= next_join:
                send_join()
                next_join = now + int(args.join_interval)

            sniff(iface=iface, filter=bpf, prn=handle, store=False, timeout=1)

    except KeyboardInterrupt:
        print("\n[RECEIVER] Ctrl+C detected.")
        try:
            send_leave()
        except Exception as e:
            print("[RECEIVER] LEAVE failed (ignored): {}".format(e))


if __name__ == "__main__":
    main()
