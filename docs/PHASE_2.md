# Phase 2 - Serverless Shared Multicast Canvas

## Objective

Phase 2 reuses the Phase 1 network and turns it into a multi-peer interactive application. Every host runs the same `mcast_canvas.py` program, sends local drawing operations to the multicast group, receives peer operations, parses JSON messages, and renders them on a shared Tkinter canvas.

## Two supported network modes

### A. PIM-SM - preferred for true many-to-many multicast

RouterOS PIM-SM makes both routed segments multicast-capable without preserving a fixed upstream/downstream traffic direction. This is the cleanest model when all three hosts can be both senders and receivers.

Use:

- `configs/routeros/pim-sm.rsc`
- `examples/commands/phase2-pim-sm-windows.txt`

In this mode, `--peer-unicast` is normally unnecessary.

![PIM-SM synchronized result](images/phase2-pim-results.png)

### B. IGMP Proxy - project-compatible mode with return-path assist

IGMP Proxy is retained to reproduce the original upstream/downstream project requirement. Multicast naturally flows from the upstream side toward joined downstream receivers. To make the interactive canvas behave bidirectionally across that topology, downstream instances can use `--peer-unicast`.

The assist does **not** replace multicast: messages are still multicast, and they are additionally unicast to learned peers when enabled. Message IDs are used for deduplication so the same operation is not drawn twice when both copies arrive.

Use:

- `configs/routeros/igmp-proxy.rsc`
- `examples/commands/phase2-igmp-proxy-windows.txt`

![IGMP Proxy synchronized result](images/phase2-igmp-proxy-results.png)

## Application architecture

The supplied source contains three major logical components:

- **`MulticastTransport`** - UDP socket creation, group membership, outgoing interface selection, TTL, multicast/unicast send, receive loop, and counters.
- **`ScapyIGMPKeepalive`** - optional periodic IGMPv2 JOIN plus LEAVE on exit for protocol visibility and membership stability.
- **`MulticastPaintApp`** - Tkinter UI, tools, serialization, peer tracking, deduplication, history, statistics, and distributed state operations.

## Network protocol

The application serializes events as compact UTF-8 JSON carried in UDP datagrams. Messages carry identifiers and type-specific fields. The submitted implementation/report describes event categories including presence (`hello`/`bye`), freehand segments/strokes, shapes, text, background changes, clear, fill, undo, and redo.

The default controls are:

- Group: `239.1.1.1`
- Port: `5000`
- TTL: `16`
- Presence interval: `5 s`
- IGMP keepalive interval: `10 s` when `--igmp` is enabled
- Maximum target packet size for final stroke packets: `1300 bytes`

Keeping application datagrams below typical Ethernet MTU is an explicit design consideration in the report.

## UI / collaboration features

The source includes a classic Paint-like interface with drawing tools, primary/secondary colors, shape fill, text, clear, save-to-PostScript, peer list, network statistics, operation history, shared undo/redo, and keyboard/mouse behaviors documented directly in the source and Phase 2 report.

## Observability

RouterOS Torch examples:

```routeros
/tool torch interface=ether1 port=5000
/tool torch interface=ether2 port=5000
```

Wireshark filter:

```text
udp.port == 5000 or igmp
```

When `--igmp` is enabled, the program optionally crafts IGMPv2 membership reports with Router Alert / TTL 1 for explicit visibility in captures. The application data itself continues to use normal UDP multicast sockets.

## Source authority

The full Phase 2 source and report are preserved verbatim in `original_submission/NE_Phase_002_Sepehr_Rajabi/`.
