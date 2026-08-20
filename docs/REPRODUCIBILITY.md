# Reproducibility Protocol

This procedure is designed to make the project reviewable as an experiment rather than only as a demonstration.

## 1. Prerequisites

- GNS3
- MikroTik RouterOS v7 appliance in GNS3/QEMU
- Three Windows VMs connected through GNS3 Clouds / host-only VMware networks as in the reports
- Python 3
- Npcap on Windows
- `pip install -r requirements.txt`
- Wireshark for packet inspection

## 2. Build the topology

Use two L2 segments:

- Upstream: PC1 -> GNS3 switch -> RouterOS `ether2`
- Downstream: PC2 + PC3 -> GNS3 switch -> RouterOS `ether1`

The submitted environment associates PC1 with VMnet15 and the downstream VMs with VMnet16/VMnet17 through GNS3 Cloud adapters.

## 3. Configure addressing

Apply `configs/routeros/base-addressing.rsc` and configure:

- PC1: `10.0.1.10/24`, gateway `10.0.1.1`
- PC2: `10.0.2.10/24`, gateway `10.0.2.1`
- PC3: `10.0.2.11/24`, gateway `10.0.2.1`

Before multicast tests, confirm ordinary unicast reachability across both subnets.

## 4. Phase 1 experiment

1. Apply `configs/routeros/igmp-proxy.rsc`.
2. Start Wireshark on the downstream segment.
3. Start PC2 and PC3 receivers using `examples/commands/phase1-windows.txt`.
4. Confirm IGMP membership reports and router query behavior.
5. Start PC1 sender.
6. Confirm multicast `TEXT` reaches both receivers.
7. Confirm receiver `PING` and sender `PONG` traverse the routed unicast return path.
8. On RouterOS, run:

```routeros
/routing igmp-proxy interface print status
/routing igmp-proxy mfc print
```

9. In Wireshark, filter on:

```text
udp.port == 5000 or igmp
```

### Phase 1 validation matrix

| Check | Expected evidence |
|---|---|
| Downstream membership | IGMP report for `239.1.1.1` from PC2/PC3 |
| Proxy forwarding state | Active MFC entry for group/source while receiver interest exists |
| Routed multicast | UDP `10.0.1.10 -> 239.1.1.1:5000` visible downstream |
| Router traversal | Packet TTL observed one lower than sender's configured TTL |
| Reverse reachability | Unicast `PING` and `PONG` on UDP/5000 |

## 5. Phase 2 - PIM-SM experiment

1. Remove IGMP Proxy state and apply `configs/routeros/pim-sm.rsc`.
2. Start all three peers with `examples/commands/phase2-pim-sm-windows.txt`.
3. Draw a unique shape or text item from each host.
4. Confirm all three canvases converge on the same state without `--peer-unicast`.
5. Exercise clear, shape/fill, text, and shared undo/redo.
6. Observe group/source state with:

```routeros
/routing pimsm uib-g print
/routing pimsm uib-sg print
```

7. Capture traffic and confirm JSON application events use `239.1.1.1:5000`.

## 6. Phase 2 - IGMP Proxy compatibility experiment

1. Restore IGMP Proxy configuration.
2. Run PC1 normally and run PC2/PC3 with `--peer-unicast --igmp` using the provided command file.
3. Draw from all three hosts.
4. Confirm upstream-originated events arrive by multicast and downstream-originated collaboration remains synchronized through the assist path where proxy asymmetry would otherwise block the multicast return direction.
5. Confirm duplicate copies do not result in duplicate rendering.

## 7. Evidence retention

For a new experimental run, store **sanitized** captures/screenshots outside `original_submission/`. Do not modify preservation files. Record:

- RouterOS version
- Python/Scapy versions
- exact commands
- host IP/interface mapping
- router mode
- packet filter
- observed group/source state
- success/failure criteria

## 8. Repository-level verification

`python scripts/verify_repo.py` performs a no-network syntax/structure check. Add `--verify-originals` to compare all preserved source artifacts against `MANIFEST.sha256`.
