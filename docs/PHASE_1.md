# Phase 1 - IGMP Proxy and Application-Level Multicast Validation

## Objective

Phase 1 demonstrates multicast distribution from an upstream sender to downstream receivers through a MikroTik RouterOS v7 router configured as an IGMP Proxy. It combines protocol-level observation (IGMP/MFC/Wireshark) with an application-level multicast "ping" pattern.

## Addressing

| Node / interface | Role | IPv4 | Gateway |
|---|---|---:|---:|
| MikroTik `ether2` | Upstream router interface | `10.0.1.1/24` | - |
| PC1 | Upstream sender | `10.0.1.10/24` | `10.0.1.1` |
| MikroTik `ether1` | Downstream router interface | `10.0.2.1/24` | - |
| PC2 | Downstream receiver 1 | `10.0.2.10/24` | `10.0.2.1` |
| PC3 | Downstream receiver 2 | `10.0.2.11/24` | `10.0.2.1` |

Group/port: `239.1.1.1:5000`. Sender multicast TTL: `16`.

## RouterOS configuration

Apply `configs/routeros/base-addressing.rsc`, verify unicast connectivity, then apply `configs/routeros/igmp-proxy.rsc`.

Core configuration:

```routeros
/routing igmp-proxy interface add interface=ether2 upstream=yes
/routing igmp-proxy interface add interface=ether1 upstream=no
```

Useful checks:

```routeros
/routing igmp-proxy interface print status
/routing igmp-proxy mfc print
```

The expected MFC state for the project group associates source `10.0.1.10` with group `239.1.1.1`, ingress `ether2`, and active downstream `ether1` while receivers are joined.

## Sender behavior

`src/phase1/sender.py`:

1. Selects the outgoing Scapy interface and source IP/MAC.
2. Maps the IPv4 multicast group to the Ethernet multicast MAC.
3. Sends UDP `TEXT` traffic to `239.1.1.1:5000` with configurable TTL (default `16`).
4. Listens for unicast UDP `PING` messages on port `5000`.
5. Resolves next-hop MAC addresses with ARP and replies with unicast `PONG`.

## Receiver behavior

`src/phase1/receiver.py`:

1. Selects the downstream interface.
2. Sends an IGMPv2 Membership Report (`JOIN`) immediately and periodically.
3. Sniffs IGMP, multicast UDP for the configured group/port, and unicast UDP directed to the receiver.
4. On multicast `TEXT`, sends a unicast `PING` back to the packet source.
5. Receives the sender's unicast `PONG`.
6. Sends IGMPv2 `LEAVE` to `224.0.0.2` on shutdown.

## Expected packet-level evidence

- IGMP Membership Reports from downstream hosts for the project group.
- IGMP queries on the downstream segment.
- UDP multicast from `10.0.1.10` to `239.1.1.1:5000`.
- Destination Ethernet multicast MAC `01:00:5e:01:01:01` for `239.1.1.1`.
- TTL observed as `15` on the downstream side when transmitted with TTL `16`, demonstrating one routed hop.
- Unicast UDP `PING`/`PONG` between receiver and sender on port `5000`.

## Run commands

See [`../examples/commands/phase1-windows.txt`](../examples/commands/phase1-windows.txt).

## Source authority

The complete Phase 1 report is preserved at:

`original_submission/NE_Phase_001_Sepehr_Rajabi/Phase_001_Report.pdf`
