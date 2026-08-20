# RouterOS v7 - Phase 1 / Phase 2 IGMP Proxy mode
# Requires base-addressing.rsc first.
# ether2 is the single upstream interface; ether1 is downstream.

/routing igmp-proxy interface add interface=ether2 upstream=yes
/routing igmp-proxy interface add interface=ether1 upstream=no

# Verification
/routing igmp-proxy interface print status
/routing igmp-proxy mfc print
