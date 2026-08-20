# RouterOS v7 - project base addressing
# Topology from the submitted reports:
#   ether2 = Upstream  (10.0.1.0/24)
#   ether1 = Downstream (10.0.2.0/24)

/ip address add address=10.0.1.1/24 interface=ether2 comment="Project upstream gateway"
/ip address add address=10.0.2.1/24 interface=ether1 comment="Project downstream gateway"
/ip address print
