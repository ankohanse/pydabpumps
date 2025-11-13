"""Constants for the DAB Pumps integration."""
import logging
import types

_LOGGER: logging.Logger = logging.getLogger(__package__)

DABSSO_API_URL = "https://dabsso.dabpumps.com"

# DABCS is used for H2D_APP
DABCS_API_URL = "https://api.eu.dabcs.it"
DABCS_API_DOMAIN = "api.eu.dabcs.it"
DABCS_INIT_URL = DABCS_API_URL + "/mobile/v1/initialconfig"
DABCS_ACCESS_TOKEN_VALID = 5*60  # 5 minutes in seconds
DABCS_REFRESH_TOKEN_VALID = 30*24*60*60 # 30 days in seconds

# DCONNECT is used for DABLIVE_APP, DCONNECT_APP and DCONNECT_WEB
DCONNECT_API_URL = "https://dconnect.dabpumps.com"
DCONNECT_API_DOMAIN = "dconnect.dabpumps.com"
DCONNECT_ACCESS_TOKEN_COOKIE = "dabcsauthtoken"
DCONNECT_ACCESS_TOKEN_VALID = 5*60  # 5 minutes in seconds
DCONNECT_REFRESH_TOKEN_COOKIE = "dabcsauthtoken"
DCONNECT_REFRESH_TOKEN_VALID = 30*60 # 30 minutes in seconds

H2D_APP_REDIRECT_URI = 'dabiopapp://Welcome'
H2D_APP_CLIENT_ID = 'h2d-mobile'
H2D_APP_CLIENT_SECRET = None

DCONNECT_APP_CLIENT_ID = 'DWT-Dconnect-Mobile'
DCONNECT_APP_CLIENT_SECRET = 'ce2713d8-4974-4e0c-a92e-8b942dffd561'
DCONNECT_APP_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 9; SM-G935F Build/PI) DConnect/2.13.1'

# Period to prevent status updates when value was recently updated
STATUS_UPDATE_HOLD = 30 # seconds

# Extra device attributes that are not in install info, but retrieved from statuses
DEVICE_ATTR_EXTRA = {
    "mac_address": ['MacWlan'],
    "sw_version": ['LvFwVersion', 'ucVersion']
}

# Known device statuses that normally don't hold a value until an action occurs
DEVICE_STATUS_STATIC = {
    "PowerShowerCountdown",
    "SleepModeCountdown",
}

HTTPX_REQUEST_TIMEOUT = 20.0