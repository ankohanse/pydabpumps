"""Constants for the DAB Pumps integration."""
from datetime import datetime, timezone
import logging

_LOGGER: logging.Logger = logging.getLogger(__package__)

DABSSO_API_URL = "https://dabsso.dabpumps.com"
DABSSO_ACCESS_TOKEN_VALID = 5*60  # 5 minutes in seconds
DABSSO_REFRESH_TOKEN_VALID = 30*24*60*60 # 30 days in seconds

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

H2D_APP_CLIENT_ID = 'h2d-mobile'
H2D_APP_CLIENT_SECRET = None
H2D_APP_REDIRECT_URI = 'dabiopapp://Welcome'
H2D_APP_DABCS_AUTH = "vwLbTh3HKJdjHRHzdEHen43PyffAc9gK"
H2D_APP_USER_AGENT = 'DabIopApp/1.8.6' 

DABLIVE_APP_CLIENT_ID = 'dablive'
DABLIVE_APP_CLIENT_SECRET = None
DABLIVE_APP_REDIRECT_URI = 'com.dabappfreemium://Login'
DABLIVE_APP_DABCS_AUTH = "oAfA7xCgFqJnk4josgdFbjPcUFRzyUY9fgo7ANLcjXUTuyoL4a4MXKRErRaUiPyJ"
DABLIVE_APP_USER_AGENT = 'DabIopApp/1.1.64'

DCONNECT_APP_CLIENT_ID = 'DWT-Dconnect-Mobile'
DCONNECT_APP_CLIENT_SECRET = 'ce2713d8-4974-4e0c-a92e-8b942dffd561'
DCONNECT_APP_REDIRECT_URI = None
DCONNECT_APP_DABCS_AUTH = "vwLbTh3HKJdjHRHzdEHen43PyffAc9gK"
DCONNECT_APP_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 9; SM-G935F Build/PI)' # DConnect/2.13.1'

DCONNECT_WEB_CLIENT_ID =  'DWT-Dconnect'
DCONNECT_WEB_CLIENT_SECRET = None
DCONNECT_WEB_REDIRECT_URI = 'https://dconnect.dabpumps.com/sso?cameFrom=/dashboard&auth_callback=1'
DCONNECT_WEB_DABCS_AUTH = "vwLbTh3HKJdjHRHzdEHen43PyffAc9gK"
DCONNECT_WEB_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 9; SM-G935F Build/PI)' # DConnect/2.13.1'

LOGIN_REPEAT_TIMEOUT_MIN = 1 # seconds
LOGIN_REPEAT_TIMEOUT_MAX = 5*60 # seconds

# WAMP is used for push messages from the H2D servers
WAMP_URL = 'wss://dconnect.dabpumps.com/wsapp'
WAMP_HOST = 'dconnect.dabpumps.com'
WAMP_PORT = 443
WAMP_REALM = 'realm1'
WAMP_AUTH_METHODS = ['ticket']
WAMP_AUTH_ID = 'iopapp'

WAMP_START_TIMEOUT = 5 # seconds
WAMP_REPEAT_TIMEOUT_MIN = 10 # seconds
WAMP_REPEAT_TIMEOUT_MAX = 60 # seconds

# Period to prevent status updates when value was recently updated
STATUS_UPDATE_HOLD = 30 # seconds

# Extra device attributes that are not in install info, but retrieved from statuses
DEVICE_ATTR_EXTRA = {
    "mac_address": ['MacWlan'],
    "sw_version": ['LvFwVersion', 'LvVersion', 'ucVersion']
}

HTTPX_REQUEST_TIMEOUT = 20.0


# Global helper functions
utcnow = lambda: datetime.now(timezone.utc)
utcmin = lambda: datetime.min.replace(tzinfo=timezone.utc)
