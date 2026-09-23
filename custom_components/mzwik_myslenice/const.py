"""Constants for the MZWiK Myślenice (eBOK) integration."""
from __future__ import annotations

DOMAIN = "mzwik_myslenice"

BASE_URL = "https://portal.mzwikmyslenice.com.pl/ebok"

# eBOK serves fresh meter readings at most once per manual visit (roughly
# quarterly), so polling once a day is plenty and keeps load on the utility
# portal negligible.
DEFAULT_SCAN_INTERVAL = 24 * 3600  # seconds

CONF_METERS = "meters"
CONF_IMPORT_VERSION = "import_version"

# Pricing (options). Unit prices in PLN per m³; the utility does not expose them
# via the API (only invoice totals), so they are entered manually and default to
# the values from a recent invoice. Water is charged on every meter; sewage only
# on meters listed in CONF_SEWAGE_METERS (a garden meter measures water that does
# not enter the sewage system, so it is water-only).
CONF_WATER_PRICE = "water_price"
CONF_SEWAGE_PRICE = "sewage_price"
CONF_SEWAGE_METERS = "sewage_meters"

DEFAULT_WATER_PRICE = 5.05
DEFAULT_SEWAGE_PRICE = 9.15

# Bumped when a fix changes what the history import produces, so existing
# installations re-import instead of keeping data from a buggy earlier run.
IMPORT_VERSION = 2

SERVICE_IMPORT_HISTORY = "import_history"
