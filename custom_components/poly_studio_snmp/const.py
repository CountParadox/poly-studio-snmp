"""Constants for the Poly Studio SNMP integration."""
from datetime import timedelta

DOMAIN = "poly_studio_snmp"

CONF_COMMUNITY = "community"
DEFAULT_PORT = 161
DEFAULT_COMMUNITY = "public"

# The device refreshes its SNMP data roughly every 15 s.
SCAN_INTERVAL = timedelta(seconds=30)

# Shared by every *Status object in POLYCOM-ENDPOINT-MIB.
STATUS_MAP = {1: "disabled", 2: "ok", 3: "failed"}
STATUS_OPTIONS = list(STATUS_MAP.values())
