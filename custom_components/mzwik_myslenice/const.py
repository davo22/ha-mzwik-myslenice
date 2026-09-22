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

# Bumped when a fix changes what the history import produces, so existing
# installations re-import instead of keeping data from a buggy earlier run.
IMPORT_VERSION = 1

SERVICE_IMPORT_HISTORY = "import_history"
