# RouterOS v7 - Phase 2 PIM-SM mode
# This switches away from IGMP Proxy to true multicast routing between both segments.
# Requires base-addressing.rsc first.

# Remove IGMP Proxy interface entries if they exist.
/routing igmp-proxy interface remove [find]

# Minimal PIM-SM configuration documented in the Phase 2 report.
/routing pimsm instance add name=pim1
/routing pimsm interface-template add interfaces=ether1,ether2 instance=pim1

# Verification after hosts join/send traffic.
/routing pimsm uib-g print
/routing pimsm uib-sg print
