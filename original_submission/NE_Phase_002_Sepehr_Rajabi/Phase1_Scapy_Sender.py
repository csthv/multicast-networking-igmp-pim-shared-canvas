# -*- coding: utf-8 -*-
"""
sender.py  (run on PC1 - upstream)

- Sends multicast UDP TEXT periodically to group:port.
- Listens for unicast PINGs on the same port and replies with unicast PONG.
- Uses Scapy + Npcap (no Python sockets).

Examples:
  py sender.py --group 239.1.1.1 --port 5000 --ttl 16 --interval 2
  py sender.py --list-ifaces
  py sender.py --iface "Ethernet"   (only if auto-pick is wrong)
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

try:
    from scapy.arch.windows import get_windows_if_list
    WINDOWS = True
except Exception:
    WINDOWS = False

DEFAULT_GROUP = "239.1.1.1"
DEFAULT_PORT = 5000
DEFAULT_TTL = 16
DEFAULT_INTERVAL = 2.0
DEFAULT_LISTEN = 1.0


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
    """
    If --iface is given -> match it.
    Else if --src-ip is given -> match interface with that IP.
    Else -> pick first interface with a real IPv4 (not 0.0.0.0).
    """
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

        raise SystemExit("[SENDER] Could not match iface '{}'. Use --list-ifaces.".format(user_iface))

    if prefer_ip:
        for n in get_if_list():
            try:
                if get_if_addr(n) == prefer_ip:
                    return n
            except Exception:
                pass
        raise SystemExit("[SENDER] No interface has IPv4={}. Use --list-ifaces or --iface.".format(prefer_ip))

    for n in get_if_list():
        try:
            ip = get_if_addr(n)
            if ip and ip != "0.0.0.0" and ip != "127.0.0.1":
                return n
        except Exception:
            pass

    raise SystemExit("[SENDER] Could not auto-pick an interface. Use --list-ifaces and --iface.")


def route_next_hop(dst_ip):
    """
    Return gateway IP if routing uses one; otherwise return dst_ip (direct).
    """
    try:
        r = conf.route.route(dst_ip)
        # (dest, netmask, gw, iface, addr) in many builds
        if isinstance(r, (list, tuple)) and len(r) >= 3:
            gw = r[2]
            if isinstance(gw, str) and gw and gw != "0.0.0.0":
                return gw
        return dst_ip
    except Exception:
        return dst_ip


def arp_resolve(iface, src_ip, src_mac, target_ip, timeout=1.0):
    """
    ARP resolve target_ip (or gateway) to a MAC address.
    """
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
    """
    For unicast across router: Ethernet dst must be next-hop MAC (gateway).
    Cache results to avoid ARPing every time.
    """
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

    ap = argparse.ArgumentParser(description="Scapy multicast sender + PONG responder (auto iface).")
    ap.add_argument("--list-ifaces", action="store_true", help="List interfaces and exit.")
    ap.add_argument("--iface", default=None, help="(Optional) Interface name/substring if auto-pick is wrong.")
    ap.add_argument("--src-ip", default=None, help="(Optional) Source IPv4 (default: interface IPv4).")
    ap.add_argument("--src-mac", default=None, help="(Optional) Spoof source MAC (default: interface MAC).")

    ap.add_argument("--group", default=DEFAULT_GROUP, help="Multicast group IP.")
    ap.add_argument("--port", default=DEFAULT_PORT, type=int, help="UDP port (also used for PING/PONG).")
    ap.add_argument("--ttl", default=DEFAULT_TTL, type=int, help="Multicast IP TTL (>=2 to cross router).")
    ap.add_argument("--interval", default=DEFAULT_INTERVAL, type=float, help="Seconds between multicast TEXT sends.")
    ap.add_argument("--listen", default=DEFAULT_LISTEN, type=float, help="Seconds to listen for PING after each send.")
    args = ap.parse_args()

    if args.list_ifaces:
        list_ifaces()
        return

    iface = pick_iface(args.iface, args.src_ip)

    src_ip = args.src_ip or get_if_addr(iface)
    if not src_ip or src_ip in ("0.0.0.0", "127.0.0.1"):
        raise SystemExit("[SENDER] Could not determine a valid src IP. Use --src-ip or --iface.")

    src_mac = args.src_mac or get_if_hwaddr(iface)

    m_dst_mac = multicast_mac(args.group)

    print("[SENDER] iface={}".format(iface))
    print("[SENDER] src_ip={}  src_mac={}".format(src_ip, src_mac))
    print("[SENDER] mcast dst={}:{}  ttl={}  interval={}s  listen={}s".format(
        args.group, args.port, args.ttl, args.interval, args.listen
    ))
    print("[SENDER] multicast dst_mac={}".format(m_dst_mac))
    print("Press Ctrl+C to stop.\n")

    # Listen for PINGs arriving at me:port
    bpf = "udp and dst port {} and dst host {}".format(args.port, src_ip)

    mac_cache = {}

    def handle_ping(pkt):
        if not (pkt and pkt.haslayer(IP) and pkt.haslayer(UDP)):
            return
        ip = pkt[IP]
        udp = pkt[UDP]
        text = extract_text(pkt)

        if int(udp.dport) != int(args.port):
            return
        if text.upper() != "PING":
            return

        rx_ip = ip.src
        print("[SENDER] <<< PING from {}:{}".format(rx_ip, int(udp.sport)))

        dst_mac = l2_dst_mac_for_unicast(iface, src_ip, src_mac, rx_ip, mac_cache)
        if not dst_mac:
            print("[SENDER] !!! ARP failed for next-hop toward {} (check gateway/ARP/firewall).".format(rx_ip))
            return

        pong = (
            Ether(src=src_mac, dst=dst_mac) /
            IP(src=src_ip, dst=rx_ip, ttl=64) /
            UDP(sport=args.port, dport=args.port) /
            Raw(load=b"PONG")
        )
        sendp(pong, iface=iface, verbose=False)
        print("[SENDER] >>> PONG to {}".format(rx_ip))

    i = 0
    try:
        while True:
            msg = "Hello multicast #{} from {}".format(i, src_ip).encode("utf-8")
            pkt = (
                Ether(src=src_mac, dst=m_dst_mac) /
                IP(src=src_ip, dst=args.group, ttl=args.ttl) /
                UDP(sport=args.port, dport=args.port) /
                Raw(load=msg)
            )
            sendp(pkt, iface=iface, verbose=False)
            print("[SENDER][MCAST] >>> {!r}".format(msg.decode("utf-8", errors="ignore")))

            sniff(iface=iface, filter=bpf, prn=handle_ping, store=False, timeout=float(args.listen))

            i += 1
            time.sleep(float(args.interval))

    except KeyboardInterrupt:
        print("\n[SENDER] Ctrl+C detected, exiting.")


if __name__ == "__main__":
    main()
