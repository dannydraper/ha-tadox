"""Constants for the Tado X integration."""

from __future__ import annotations

DOMAIN = "tadox"

# OAuth2 device-code flow (tado's public app id).
CLIENT_ID = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"
SCOPE = "offline_access"
DEVICE_AUTH_URL = "https://login.tado.com/oauth2/device_authorize"
TOKEN_URL = "https://login.tado.com/oauth2/token"

# API hosts. tado X device data lives on hops.tado.com; account and weather
# are still served by the older my.tado.com v2 API.
ME_URL = "https://my.tado.com/api/v2/me"
MY_API = "https://my.tado.com/api/v2"
HOPS_API = "https://hops.tado.com"

# Config entry / options keys.
CONF_TOKENS = "tokens"
CONF_HOME_ID = "home_id"
CONF_HOME_NAME = "home_name"
CONF_SCAN_INTERVAL = "scan_interval"

# Polling. tado limits the API per day (we measured ~1000/day on a free
# account), so we poll room state on the main interval and fetch the heavier,
# slower-changing device/weather data only every Nth cycle.
DEFAULT_SCAN_INTERVAL = 300  # seconds
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600
SLOW_CYCLE_EVERY = 6  # fetch devices + weather every 6th room poll (~30 min)

# Weather cutoff ("don't heat when it's mild enough outside"). Persisted in a
# small Store (not the config entry, so toggling it doesn't reload the entry).
DEFAULT_WEATHER_CUTOFF_TEMP = 15.0  # °C
MIN_CUTOFF_TEMP = 5.0
MAX_CUTOFF_TEMP = 30.0
STORAGE_VERSION = 1

# Manufacturer string for the device registry.
MANUFACTURER = "tado°"
