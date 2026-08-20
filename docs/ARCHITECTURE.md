# Architecture

## System view

```text
                      Control plane / membership
        IGMPv2 reports ------------------------------+
                                                      v
+----------------+      multicast UDP       +----------------------+      multicast UDP      +----------------+
| PC1 / Upstream |  <-------------------->  | MikroTik RouterOS v7 |  <------------------->  | PC2 + PC3      |
| 10.0.1.10      |                          | ether2 / ether1      |                         | 10.0.2.10/.11  |
+----------------+                          +----------------------+                         +----------------+
       |                                             |
       | Phase 1: sender                             | IGMP Proxy or PIM-SM
       | Phase 2: peer                               |
       +---------------------------------------------+

Phase 1 return path: receiver unicast PING -> sender; sender unicast PONG -> receiver.
Phase 2 IGMP-Proxy mode: optional peer-unicast duplicates selected peer traffic while multicast remains primary.
```

## Phase 1 data/control separation

**Control plane:** IGMP membership reports and queries allow the router/proxy to know where group interest exists. RouterOS exposes proxy-interface status and MFC state.

**Data plane:** the sender transmits UDP to the multicast group; the router forwards traffic to the downstream interface where membership exists. Receiver-generated PING and sender-generated PONG use ordinary unicast IP forwarding and therefore test the reverse path independently of multicast forwarding.

## Phase 2 application layering

```text
Tkinter interaction / rendering
            |
            v
Operation model + deterministic IDs + history / undo / redo
            |
            v
Compact JSON message encoding
            |
            v
MulticastTransport (UDP socket, membership, TTL, counters)
            |                       \
            |                        +--> optional peer-unicast assist
            v
239.1.1.1:5000

Optional sidecar: ScapyIGMPKeepalive -> IGMPv2 JOIN/LEAVE for observability.
```

## Why the two router modes matter

IGMP Proxy is asymmetric by design in this experiment: one interface is designated upstream and the downstream side expresses group interest. That structure matches Phase 1 but does not naturally model a fully symmetric multi-sender application.

PIM-SM changes the problem from proxying membership to multicast routing. In the project's one-router/two-segment topology, it provides the more natural Phase 2 model because peers on either side can act as sources while the router maintains multicast state between interfaces.

The `--peer-unicast` mechanism is therefore best understood as a compatibility assist for the required IGMP-Proxy experiment, not as a replacement for multicast routing.
