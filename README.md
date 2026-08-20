# Two-Stage IP Multicast Networking Project

**IGMP Proxy, Scapy-based multicast validation, PIM-SM, and a serverless shared multicast canvas in GNS3 / MikroTik RouterOS v7**

This repository is a GitHub-ready, reproducibility-focused edition of the supplied two-stage Internet Engineering / computer-networking project. It preserves the complete submitted reports, code, command notes, packet capture, and demonstration video while exposing the implementation in a clean source tree suitable for review, reproduction, and academic citation.

> **Preservation guarantee:** the supplied project files are retained unmodified under [`original_submission/`](original_submission/). The clearer files under `src/`, `configs/`, `examples/`, and `docs/` are organization/reproducibility layers around that submission.

![GNS3 multicast topology](docs/images/topology-gns3.png)

## Project at a glance

| Dimension | Phase 1 | Phase 2 |
|---|---|---|
| Main objective | Validate multicast delivery and IGMP behavior across routed upstream/downstream segments | Build a real-time shared Paint-like canvas over multicast |
| Router mode | IGMP Proxy | IGMP Proxy + peer-unicast assist, or PIM-SM for true bidirectional multicast routing |
| Application transport | Scapy-crafted Ethernet/IP/UDP plus IGMPv2 JOIN/LEAVE | Python UDP multicast sockets; optional Scapy IGMP keepalive |
| Multicast group | `239.1.1.1` | `239.1.1.1` |
| UDP port | `5000` | `5000` |
| Multicast TTL | `16` from sender | `16` by default |
| Evidence | RouterOS IGMP/MFC state, Wireshark, sender/receiver console behavior | Three synchronized GUI instances, RouterOS Torch, Wireshark/JSON traffic, PCAP, demo video |

## Network topology

```text
                              MikroTik RouterOS v7

 PC1 / Upstream              ether2       ether1                Downstream LAN
 10.0.1.10/24  ---- Switch ----|  10.0.1.1   10.0.2.1 |---- Switch ---- PC2 10.0.2.10/24
 Gateway 10.0.1.1             |                     |             |----- PC3 10.0.2.11/24
                               +---------------------+                   GW 10.0.2.1

 Multicast group: 239.1.1.1        UDP port: 5000        TTL used: 16
```

The submitted GNS3 design uses `ether2` as the upstream side and `ether1` as the downstream side. PC1 is the upstream sender in Phase 1; PC2 and PC3 are downstream receivers. Phase 2 runs the same canvas application on all three hosts.

## Repository layout

```text
.
├── src/
│   ├── phase1/
│   │   ├── sender.py
│   │   └── receiver.py
│   └── phase2/
│       └── mcast_canvas.py
├── configs/routeros/
│   ├── base-addressing.rsc
│   ├── igmp-proxy.rsc
│   └── pim-sm.rsc
├── examples/commands/
├── docs/
│   ├── PHASE_1.md
│   ├── PHASE_2.md
│   ├── ARCHITECTURE.md
│   ├── REPRODUCIBILITY.md
│   ├── EVIDENCE.md
│   ├── ORIGINAL_MATERIALS.md
│   └── GITHUB_UPLOAD_GUIDE.md
├── evidence/
│   └── captures/Wireshark.pcapng
├── original_submission/       # all supplied files preserved verbatim
├── scripts/verify_repo.py
├── CITATION.cff
├── requirements.txt
└── MANIFEST.sha256
```

## Publish with GitHub Desktop

This edition is prepared for **GitHub Desktop with ordinary Git and no Git LFS**. After extracting the ZIP, use **File → Add Local Repository**, select this project folder, review the complete initial change set, commit to `main`, and choose **Publish repository**. See [`GITHUB_DESKTOP_QUICKSTART.txt`](GITHUB_DESKTOP_QUICKSTART.txt) or the full [`GitHub Desktop upload guide`](docs/GITHUB_UPLOAD_GUIDE.md).

## Quick start

### 1. Prepare the lab

Use GNS3 with a RouterOS v7 router and the two logical L2 segments shown above. Configure the IP addresses in [`configs/routeros/base-addressing.rsc`](configs/routeros/base-addressing.rsc), then select either IGMP Proxy or PIM-SM mode.

### 2. Install the Python dependency

```bash
python -m pip install -r requirements.txt
```

On **Windows**, install **Npcap** as well. Phase 1 sends/sniffs raw Ethernet frames through Scapy, and Phase 2 needs Scapy/Npcap when `--igmp` is enabled. Tkinter is part of the normal Windows Python distribution.

### 3. Run Phase 1

Use the commands in [`examples/commands/phase1-windows.txt`](examples/commands/phase1-windows.txt). In the intended experiment, PC1 multicasts text packets and listens for unicast `PING`; each downstream receiver sends IGMPv2 membership reports, receives the multicast payload, unicasts `PING` to PC1, and observes `PONG` in response.

### 4. Run Phase 2

For the academically cleaner many-to-many multicast case, configure PIM-SM and use [`phase2-pim-sm-windows.txt`](examples/commands/phase2-pim-sm-windows.txt). To reproduce the project's IGMP Proxy mode, use [`phase2-igmp-proxy-windows.txt`](examples/commands/phase2-igmp-proxy-windows.txt); downstream nodes add `--peer-unicast` because IGMP Proxy is naturally oriented around an upstream source and downstream receivers.

![Phase 2 PIM-SM synchronized canvas](docs/images/phase2-pim-results.png)

## What the Phase 2 application implements

The supplied Phase 2 program is a single peer application for every host. It provides a Tkinter Paint-like UI, multicast transport, JSON event serialization, peer presence (`hello`/`bye`), optional IGMPv2 JOIN/LEAVE visibility through Scapy, deduplication, live statistics/history, clear/background/text/shape/freehand operations, and distributed undo/redo. The code intentionally retains multicast as the primary transport even when `--peer-unicast` is enabled as an assist mechanism.

## Evidence and validation

The repository includes the original Wireshark capture and demo video, plus extracted documentation figures for rapid review. A useful Wireshark display filter from the submitted report is:

```text
udp.port == 5000 or igmp
```

The report also uses the TTL transition from `16` at transmission to `15` after one routed hop as packet-level evidence that multicast crossed the router.

![Wireshark multicast evidence](docs/images/wireshark-capture.png)

See [`docs/EVIDENCE.md`](docs/EVIDENCE.md) for the evidence map and [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for a controlled reproduction procedure.

## Integrity and verification

Run the non-networking repository check:

```bash
python scripts/verify_repo.py
```

To additionally verify the SHA-256 hashes of every preserved original file:

```bash
python scripts/verify_repo.py --verify-originals
```

The canonical `src/` copies are intentionally function-preserving reorganizations of the supplied source. The original filenames remain available in `original_submission/`.

## Academic use and citation

A [`CITATION.cff`](CITATION.cff) file is included so GitHub can expose a standard **Cite this repository** entry. The complete submitted PDF reports remain the authoritative narrative source for methodology, screenshots, interpretation, and conclusions.

No open-source license was selected automatically because licensing is an author decision. Add an appropriate license before inviting reuse beyond normal academic review.

## Public-repository privacy note

Before making the repository public, inspect the original PDF reports, packet capture, screenshots, and video. The original academic materials can contain student identifiers, hostnames, IP addressing, or other environment-specific information. They are preserved here because the GitHub-ready package was requested to omit none of the supplied work.

## Documentation

- [`Phase 1`](docs/PHASE_1.md) - topology, IGMP Proxy, Scapy sender/receiver, expected observations.
- [`Phase 2`](docs/PHASE_2.md) - shared-canvas protocol, peer-unicast assist, PIM-SM mode, UI behavior.
- [`Architecture`](docs/ARCHITECTURE.md) - control/data-plane view and message flow.
- [`Reproducibility`](docs/REPRODUCIBILITY.md) - step-by-step experimental procedure and validation matrix.
- [`Evidence`](docs/EVIDENCE.md) - reports, PCAP, figures, video, Wireshark/Torch observations.
- [`Original materials`](docs/ORIGINAL_MATERIALS.md) - mapping from submitted files to the organized repository.
- [`GitHub upload guide`](docs/GITHUB_UPLOAD_GUIDE.md) - GitHub Desktop upload instructions for this exact repository, using ordinary Git with no LFS.
