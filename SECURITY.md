# Security and Lab-Safety Notes

This repository is an academic networking laboratory project. It intentionally creates raw Ethernet/IP/IGMP/UDP traffic and modifies multicast behavior.

- Run it only on lab networks, isolated virtual networks, or networks where you have permission.
- Scapy raw-packet operations may require administrator/root privileges.
- On Windows, Npcap is required for the Scapy-based Phase 1 programs and for Phase 2 when `--igmp` is used.
- Review local firewall policy before opening UDP/5000.
- Do not apply the RouterOS snippets blindly to production routers. Interface names, addressing, and firewall policy must match the target environment.
- The original reports and demo evidence may contain identifying or environment-specific information. Review them before publishing the repository publicly.
