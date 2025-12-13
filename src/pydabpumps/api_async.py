"""api.py: DabPumps API for DAB Pumps integration."""

import base64
import copy
import hashlib
import jwt
import math
import os
import warnings
import asyncio
import httpx
import json
import logging
import re
import time

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from enum import Enum, StrEnum
from typing import Any
from urllib.parse import urlparse, parse_qs


from .const import (
    DABSSO_API_URL,
    DCONNECT_API_URL,
    DCONNECT_API_DOMAIN,
    DCONNECT_ACCESS_TOKEN_COOKIE,
    DCONNECT_ACCESS_TOKEN_VALID,
    DCONNECT_REFRESH_TOKEN_COOKIE,
    DCONNECT_REFRESH_TOKEN_VALID,
    DABCS_INIT_URL,
    DABCS_API_URL,
    DABCS_API_DOMAIN,
    DABCS_ACCESS_TOKEN_VALID,
    DABCS_REFRESH_TOKEN_VALID,
    DEVICE_ATTR_EXTRA,
    DEVICE_STATUS_STATIC,
    H2D_APP_REDIRECT_URI,
    H2D_APP_CLIENT_ID,
    H2D_APP_CLIENT_SECRET,
    DCONNECT_APP_CLIENT_ID,
    DCONNECT_APP_CLIENT_SECRET,
    DCONNECT_APP_USER_AGENT,
    STATUS_UPDATE_HOLD,
    HTTPX_REQUEST_TIMEOUT,
)

from .data import (
    DabPumpsError,
    DabPumpsConnectError,
    DabPumpsAuthError,
    DabPumpsDataError,
    DabPumpsUserRole,
    DabPumpsParamType,
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsConfig,
    DabPumpsParams,
    DabPumpsStatus,
    DabPumpsHistoryItem,
    DabPumpsHistoryDetail,
)

_LOGGER = logging.getLogger(__name__)


class DabPumpsLogin(StrEnum):
    ACCESS_TOKEN = 'Access-Token'
    REFRESH_TOKEN = 'Refresh-Token'
    H2D_APP = 'H2D-app'                 # Uses DabCS with Authorization Header
    DABLIVE_APP_0 = 'DabLive-app_0'     # Uses DConnect with Authorization Header
    DABLIVE_APP_1 = 'DabLive-app_1'     # Uses DConnect with Authorization Header
    DCONNECT_APP = 'DConnect-app'       # Uses DConnect with Authorization Header
    DCONNECT_WEB = 'DConnect-web'       # Uses DConnect with Cookie

class DabPumpsFetch(StrEnum):
    DABCS = DABCS_API_DOMAIN,
    DCONNECT = DCONNECT_API_DOMAIN

class DabPumpsAuth(StrEnum):
    HEADER = "Authorization Header"
    COOKIE = "Cookie"


# DabPumps api to detect device and get device info, fetch the actual data from the device, and parse it
class AsyncDabPumps:
    
    def __init__(self, username, password, client:httpx.AsyncClient|None = None):
        # Configuration
        self._username: str = username
        self._username: str = username
        self._password: str = password

        # Login data
        self._login_time: datetime|None = None
        self._login_method: DabPumpsLogin|None = None
        self._fetch_method: DabPumpsFetch|None = None
        self._auth_method: DabPumpsAuth|None = None
        self._extra_headers = {}

        self._access_token: str|None = None
        self._access_expires_in: int|None = None
        self._access_expiry: datetime|None = None
        self._refresh_token: str|None = None
        self._refresh_expires_in: int|None = None
        self._refresh_expiry: datetime|None = None
        self._refresh_client_id = None
        self._refresh_client_secret = None

        # Retrieved data
        self._install_map: dict[str, DabPumpsInstall] = {}
        self._device_map: dict[str, DabPumpsDevice] = {}
        self._config_map: dict[str, DabPumpsConfig] = {}
        self._status_actual_map: dict[str, DabPumpsStatus] = {}
        self._status_static_map: dict[str, DabPumpsStatus] = {}
        self._string_map: dict[str, str] = {}
        self._string_map_lang: str = None

        self._install_map_ts: datetime = datetime.min
        self._device_map_ts: datetime = datetime.min
        self._device_detail_ts: datetime = datetime.min
        self._config_map_ts: datetime = datetime.min
        self._status_actual_map_ts: datetime = datetime.min
        self._status_static_map_ts: datetime = datetime.min
        self._string_map_ts: datetime = datetime.min

        # Http Client; we keep the same client for the whole life of the api instance.
        self._http_client: httpx.AsyncClient = client or httpx.AsyncClient()
        self._http_client_close = False if client else True     # Do not close an external passed client

        # Locks to protect certain operations from being called from multiple threads
        self._login_lock = asyncio.Lock()

        # To pass diagnostics data back to our parent
        self._diagnostics_callback = None


    def set_diagnostics(self, callback):
        self._diagnostics_callback = callback


    @staticmethod
    def create_id(*args):
        str = '_'.join(args).strip('_')
        str = re.sub(' ', '_', str)
        str = re.sub('[^a-z0-9_-]+', '', str.lower())
        return str            
    
    
    @property
    def login_method(self) -> str:
        return self._login_method
    
    @property
    def install_map(self) -> dict[str, DabPumpsInstall]:
        return self._install_map
    
    @property
    def device_map(self) -> dict[str, DabPumpsDevice]:
        return self._device_map
    
    @property
    def config_map(self) -> dict[str, DabPumpsConfig]:
        return self._config_map
    
    @property
    def status_map(self) -> dict[str, DabPumpsStatus]:
        return self._status_static_map | self._status_actual_map
    
    @property
    def string_map(self) -> dict[str, str]:
        return self._string_map
    
    @property
    def string_map_lang(self) -> str:
        return self._string_map_lang

    @property
    def install_map_ts(self) -> datetime:
        return self._install_map_ts
    
    @property
    def device_map_ts(self) -> datetime:
        return self._device_map_ts
    
    @property
    def device_detail_ts(self) -> datetime:
        return self._device_detail_ts
    
    @property
    def config_map_ts(self) -> datetime:
        return self._config_map_ts
    
    @property
    def status_map_ts(self) -> datetime:
        return max( [self._status_static_map_ts, self._status_actual_map_ts] )
    
    @property
    def string_map_ts(self) -> datetime:
        return self._string_map_ts
    
    @property
    def closed(self) -> bool:
        """Returns whether the DabPumps api has been closed."""
        if self._http_client:
            return self._http_client.is_closed
        else:
            return True
        

    async def close(self):
        """Safely logout and close all client handles"""
        if self._http_client is not None and self._http_client_close:
            await self._http_client.aclose()
            self._http_client = None


    async def login(self):
        """
        Login to DAB Pumps by trying each of the possible login methods.
        Guards for calls from multiple threads.
        """

        # Only one thread at a time can check token cookie and do subsequent login if needed.
        # Once one thread is done, the next thread can then check the (new) token cookie.
        async with self._login_lock:
            await self._login()


    async def _login(self):
        """Login to DAB Pumps by trying each of the possible login methods"""        

        # We have four possible login methods that all seem to work for both DConnect (non-expired) and for DAB Live
        # First try to keep using the access token
        # Next, try to refresh that token.
        # Then, try the method that succeeded last time!
        # Finally try all logig methods
        error = None
        methods = [DabPumpsLogin.ACCESS_TOKEN, DabPumpsLogin.REFRESH_TOKEN, self._login_method, DabPumpsLogin.H2D_APP, DabPumpsLogin.DABLIVE_APP_1, DabPumpsLogin.DABLIVE_APP_0, DabPumpsLogin.DCONNECT_APP, DabPumpsLogin.DCONNECT_WEB]
        for method in methods:
            try:
                match method:
                    case DabPumpsLogin.ACCESS_TOKEN:
                        # Try to keep using the Access Token
                        success = await self._login_access_token()
                    case DabPumpsLogin.REFRESH_TOKEN:
                        # Try to refresh the token
                        success = await self._login_refresh_token()
                    case DabPumpsLogin.H2D_APP:
                        # Try the procedure of the H2D app (most up to date)
                        success = await self._login_h2d_app()
                    case DabPumpsLogin.DABLIVE_APP_1: 
                        # Try the simplest method
                        success = await self._login_dablive_app(isDabLive=1)
                    case DabPumpsLogin.DABLIVE_APP_0:
                        # Try the alternative simplest method
                        success = await self._login_dablive_app(isDabLive=0)
                    case DabPumpsLogin.DCONNECT_APP:
                        # Try the method that uses 2 steps
                        success = await self._login_dconnect_app()
                    case DabPumpsLogin.DCONNECT_WEB:
                        # Finally try the most complex and unreliable one
                        success = await self._login_dconnect_web()
                    case _:
                        # No previously known login method was set yet
                        success =  False

                if success:
                    # if we reached this point then a login method succeeded
                    return 
            
            except Exception as ex:
                error = ex

                # Clear any previous login cookies and tokens before trying the next method
                await self._logout(context="login", method=method)

        # if we reached this point then all methods failed.
        if error:
            raise error
        

    async def _login_access_token(self) -> bool:
        """Inspect whether the access token is still valid"""

        match self._auth_method:
            case DabPumpsAuth.COOKIE: access_token = self._http_client.cookies.get(name=DCONNECT_ACCESS_TOKEN_COOKIE, domain=DCONNECT_API_DOMAIN)
            case DabPumpsAuth.HEADER: access_token = self._access_token
            case _: access_token = None

        if not access_token or not self._access_expiry:
            # No acces-token to check; silently continue to the next login method (token refresh)
            return False

        # Dab Pumps seems to ignore the expiry field inside the token, using only
        # the expires_in field that was passed alongside the token.
        if datetime.now() > self._access_expiry:
            _LOGGER.debug(f"Access-Token expired")
            return False    # silently continue to the next login method (token refresh)

        # Re-use this access token
        context = f"login access_token reuse"
        token = {
            "access_token": access_token,
            "access_expires_in": self._access_expires_in,
            "access_expiry": self._access_expiry,
        }
        await self._update_diagnostics(datetime.now(), context, None, None, token)

        _LOGGER.debug(f"Reuse the access-token")
        return True


    async def _login_refresh_token(self) -> bool:
        """Attempty to refresh the access token"""

        match self._auth_method:
            case DabPumpsAuth.COOKIE: refresh_token = self._http_client.cookies.get(name=DCONNECT_REFRESH_TOKEN_COOKIE, domain=DCONNECT_API_DOMAIN)
            case DabPumpsAuth.HEADER: refresh_token = self._refresh_token
            case _: refresh_token = None

        if not refresh_token:
            # No refresh-token; silently continue to the next login method
            return False
        
        if self._auth_method == DabPumpsAuth.COOKIE:
            # The tokens cookies should automatically be refreshed during periodic calls.
            # If we get to this point then somehow the access-token and refresh-token cookies
            # have expired; silently continue to the next login method 
            return False
        
        # Don't bother to check the contents of the refresh token, 
        # just attempt to request a new access token via the refresh token
        context = f"login access_token refresh"
        request = {
            "method": "POST",
            "url": DABSSO_API_URL + '/auth/realms/dwt-group/protocol/openid-connect/token',
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'grant_type': 'refresh_token',
                'refresh_token': self._refresh_token, 
                'client_id': self._refresh_client_id or "",
                'client_secret': self._refresh_client_secret or "",
            },
        }
        
        _LOGGER.debug(f"Try refresh the access-token; authenticate via {request["method"]} {request["url"]}")
        result = await self._send_request(context, request)

        # Store access-token in variable so it will be added as Authorization header in calls to DABCS and DConnect
        # We do not need to store the new access-token as cookie, those take care of their own refresh
        self._access_token = self._validate_token( result.get('access_token') )
        self._access_expires_in = self._validate_expires_in( result.get('expires_in'), DCONNECT_ACCESS_TOKEN_VALID )
        self._access_expiry = self._calculate_expiry(self._access_expires_in)

        self._refresh_token = self._validate_token( result.get('refresh_token') )
        self._refresh_expires_in = self._validate_expires_in( result.get('refresh_expires_in'), DCONNECT_REFRESH_TOKEN_VALID)
        self._refresh_expiry = self._calculate_expiry(self._refresh_expires_in)

        if not self._access_token or not self._refresh_token:
            error = f"No tokens found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)

        # The refresh of the tokens succeeded
        _LOGGER.debug(f"Refreshed the access-token; original login used method {self._login_method}")
        return True


    async def _login_h2d_app(self) -> bool:
        """Login to DAB Pumps via the method as used by the H2D app"""

        # Step 0: generate an unique state and a code challenge
        state_bytes = os.urandom(16)
        openid_state_req = base64.urlsafe_b64encode(state_bytes).decode('utf-8').rstrip('=')

        openid_code_bytes = os.urandom(86)
        openid_code_verifier = base64.urlsafe_b64encode(openid_code_bytes).decode('utf-8').rstrip('=')
        openid_hashed_verifier = hashlib.sha256(openid_code_verifier.encode('utf-8')).digest()
        openid_code_challenge = base64.urlsafe_b64encode(openid_hashed_verifier).decode('utf-8').rstrip('=')

        openid_client_id = H2D_APP_CLIENT_ID
        openid_client_secret = H2D_APP_CLIENT_SECRET

        # Step 1: get login url
        context = f"login H2D_app openid-connect auth"
        request = {
            "method": "GET",
            "url": DABSSO_API_URL + '/auth/realms/dwt-group/protocol/openid-connect/auth',
            'params': {
                'client_id': openid_client_id,
                'response_type': 'code',
                'code_challenge': openid_code_challenge,
                'code_challenge_method': 'S256',
                'state': openid_state_req,
                'scope': 'openid profile email phone',
                'redirect_uri': H2D_APP_REDIRECT_URI,
            },
        }

        _LOGGER.debug(f"Try login with H2D; retrieve auth page via {request["method"]}  {request["url"]}")
        text = await self._send_request(context, request)
        
        match = re.search(r'action\s?=\s?\"(.*?)\"', text, re.MULTILINE)
        if not match:    
            error = f"Unexpected response while retrieving openid-connect from {request["url"]}: {text}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)
        
        # Step 2: Authenticate
        context = f"login H2D_app authenticate"
        request = {
            "method": "POST",
            "url": match.group(1).replace('&amp;', '&'),
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'username': self._username, 
                'password': self._password,
            },
            "flags": {
                'redirects': False,
            }
        }
        
        _LOGGER.debug(f"Try login with H2D; authenticate '{self._username}' via {request["method"]} {request["url"]}")
        location_str = await self._send_request(context, request)

        # Returned value is a redirect location containing state and session_state
        if not location_str.startswith(H2D_APP_REDIRECT_URI) or not "code=" in text:
            error = f"Unexpected response while authenticating from {request["url"]}: {text}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)
        
        location_url = urlparse(location_str)
        openid_state_rsp = parse_qs(location_url.query).get('state')[0]
        openid_code = parse_qs(location_url.query).get('code')[0]

        if openid_state_rsp != openid_state_req:
            _LOGGER.debug(f"Unexpected state value in response while authenticating: '{openid_state_rsp}', expected '{openid_state_req}")

        # Step 3: Get Access and Refresh Tokens
        context = f"login H2D_app openid-connect token"
        request = {
            "method": "POST",
            "url": DABSSO_API_URL + '/auth/realms/dwt-group/protocol/openid-connect/token',
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'grant_type': 'authorization_code',
                'code': openid_code, 
                'code_verifier': openid_code_verifier,
                'client_id': openid_client_id,
                'redirect_uri': H2D_APP_REDIRECT_URI,
            },
        }
        
        _LOGGER.debug(f"Try login with H2D; retrieve tokens via {request["method"]} {request["url"]}")
        result = await self._send_request(context, request)

        self._access_token = self._validate_token( result.get('access_token') )
        self._access_expires_in = self._validate_expires_in( result.get('expires_in'), DABCS_ACCESS_TOKEN_VALID )
        self._access_expiry = self._calculate_expiry(self._access_expires_in)

        self._refresh_token = self._validate_token( result.get('refresh_token') )
        self._refresh_expires_in = self._validate_expires_in( result.get('refresh_expires_in'), DABCS_REFRESH_TOKEN_VALID)
        self._refresh_expiry = self._calculate_expiry(self._refresh_expires_in)
        self._refresh_client_id = openid_client_id
        self._refresh_client_secret = openid_client_secret

        if not self._access_token:
            error = f"No tokens found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)

        # if we reach this point then the token was OK
        self._login_time = datetime.now()
        self._login_method = DabPumpsLogin.H2D_APP
        self._fetch_method = DabPumpsFetch.DABCS
        self._auth_method = DabPumpsAuth.HEADER
        self._extra_headers = {}

        _LOGGER.debug(f"Login succeeded using method {self._login_method}")
        return True

        
    async def _login_dablive_app(self, isDabLive=1) -> bool:
        """Login to DAB Pumps via the method as used by the DAB Live app"""

        # Step 1: get authorization token
        context = f"login via DabLive App (isDabLive={isDabLive})"
        request = {
            "method": "POST",
            "url": DCONNECT_API_URL + f"/auth/token",
            "params": {
                'isDabLive': isDabLive,     # required param, though actual value seems to be completely ignored
            },
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'username': self._username, 
                'password': self._password,
            },
        }
        
        _LOGGER.debug(f"Try login with DabLive; authenticate '{self._username}' via {request["method"]} {request["url"]} with isDabLive={isDabLive}")
        result = await self._send_request(context, request)

        self._access_token = self._validate_token( result.get('access_token') )
        self._access_expires_in = self._validate_expires_in( result.get('expires_in'), DCONNECT_ACCESS_TOKEN_VALID )
        self._access_expiry = self._calculate_expiry(self._access_expires_in)

        self._refresh_token = self._validate_token( result.get('refresh_token') )    # expected to be empty
        self._refresh_expires_in = self._validate_expires_in( result.get('refresh_expires_in'), DCONNECT_REFRESH_TOKEN_VALID)
        self._refresh_expiry = self._calculate_expiry(self._refresh_expires_in)
        self._refresh_client_id = None
        self._refresh_client_secret = None

        if not self._access_token:
            error = f"No tokens found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)

        # if we reach this point then the token was OK
        self._login_time = datetime.now()
        self._login_method = DabPumpsLogin.DABLIVE_APP_1 if isDabLive else DabPumpsLogin.DABLIVE_APP_0
        self._fetch_method = DabPumpsFetch.DCONNECT
        self._auth_method = DabPumpsAuth.HEADER
        self._extra_headers = {}

        _LOGGER.debug(f"Login succeeded using method {self._login_method}")
        return True

        
    async def _login_dconnect_app(self) -> bool:
        """Login to DAB Pumps via the method as used by the DConnect app"""

        # Step 1: get authorization token
        openid_client_id = DCONNECT_APP_CLIENT_ID
        openid_client_secret = DCONNECT_APP_CLIENT_SECRET

        context = f"login DConnect_app"
        request = {
            "method": "POST",
            "url": DABSSO_API_URL + f"/auth/realms/dwt-group/protocol/openid-connect/token",
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'client_id': openid_client_id,
                'client_secret': openid_client_secret,
                'scope': 'openid',
                'grant_type': 'password',
                'username': self._username, 
                'password': self._password 
            },
        }
        
        _LOGGER.debug(f"Try login with DConnect (app); authenticate '{self._username}' via {request["method"]} {request["url"]}")
        result = await self._send_request(context, request)

        self._access_token = self._validate_token( result.get('access_token') )
        self._access_expires_in = self._validate_expires_in( result.get('expires_in'), DCONNECT_ACCESS_TOKEN_VALID )
        self._access_expiry = self._calculate_expiry(self._access_expires_in)

        self._refresh_token = self._validate_token( result.get('refresh_token') )    # expected to be empty
        self._refresh_expires_in = self._validate_expires_in( result.get('refresh_expires_in'), DCONNECT_REFRESH_TOKEN_VALID)
        self._refresh_expiry = self._calculate_expiry(self._refresh_expires_in)
        self._refresh_client_id = openid_client_id
        self._refresh_client_secret = openid_client_secret

        if not self._access_token:
            error = f"No tokens found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)

        # if we reach this point then the token was OK
        self._login_time = datetime.now()
        self._login_method = DabPumpsLogin.DCONNECT_APP
        self._fetch_method = DabPumpsFetch.DCONNECT
        self._auth_method = DabPumpsAuth.HEADER
        self._extra_headers = { "User-Agent": DCONNECT_APP_USER_AGENT }
        
        _LOGGER.debug(f"Login succeeded using method {self._login_method}")
        return True


    async def _login_dconnect_web(self) -> bool:
        """Login to DAB Pumps via the method as used by the DConnect website"""

        # Step 1: get login url
        context = f"login DConnect_web home"
        request = {
            "method": "GET",
            "url": DCONNECT_API_URL,
        }

        _LOGGER.debug(f"Try login with DConnect (web); retrieve login page via {request["method"]} {request["url"]}")
        text = await self._send_request(context, request)
        
        match = re.search(r'action\s?=\s?\"(.*?)\"', text, re.MULTILINE)
        if not match:    
            error = f"Unexpected response while retrieving login url from {request["url"]}: {text}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)
        
        # Step 2: Login
        context = f"login DConnect_web login"
        request = {
            "method": "POST",
            "url": match.group(1).replace('&amp;', '&'),
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'username': self._username, 
                'password': self._password 
            },
        }
        
        _LOGGER.debug(f"Try login with DConnect (web); authenticate '{self._username}' via {request["method"]} {request["url"]}")
        await self._send_request(context, request)

        # Verify the client access_token cookie has been set
        access_token = self._http_client.cookies.get(name=DCONNECT_ACCESS_TOKEN_COOKIE, domain=DCONNECT_API_DOMAIN)
        if not access_token:
            error = f"No access token found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsAuthError(error)

        # if we reach this point without exceptions then login was successfull
        # Cookie for access_token is already set by the last call
        # No need to remember access-token, we never need to pass it as header with this login method
        self._access_token = None
        self._access_expires_in = None
        self._access_expiry = datetime.max  # Always let access-token expiry check succeed

        self._refresh_token = None
        self._refresh_expires_in = None
        self._refresh_expiry = datetime.max # Always let refresh-token expiry check succeed
        self._refresh_client_id = None
        self._refresh_client_secret = None

        # Set other login parameters
        self._login_time = datetime.now()
        self._login_method = DabPumpsLogin.DCONNECT_WEB
        self._fetch_method = DabPumpsFetch.DCONNECT
        self._auth_method = DabPumpsAuth.COOKIE
        self._extra_headers = {}

        _LOGGER.debug(f"Login succeeded using method {self._login_method}")
        return True

        
    async def logout(self):
        """Logout from DAB Pumps"""

        # Only one thread at a time can check token cookie and do subsequent login or logout if needed.
        # Once one thread is done, the next thread can then check the (new) token cookie.
        async with self._login_lock:
            await self._logout(context="", method=None)


    async def _logout(self, context: str, method: DabPumpsLogin|None = None):
        # Note: do not call 'async with self._login_lock' here.
        # It will result in a deadlock as login calls _logout from within its lock

        # Sanitize parameters
        context = context.lower() if context else ""

        # Reduce amount of tracing to only when we are actually logged-in.
        if self._login_time and method not in [DabPumpsLogin.ACCESS_TOKEN]:
            _LOGGER.debug(f"Logout")

        # Home Assistant will issue a warning when calling aclose() on the async aiohttp client.
        # Instead of closing we will simply forget all cookies. The result is that on a next
        # request, the client will act like it is a new one.
        self._http_client.cookies.clear()

        self._access_token = None
        self._access_expires_in = None
        self._access_expiry = None

        # Do not clear refresh token when called in a 'login' context and when we were 
        # only checking the access_token
        if not (context.startswith("login") and method in [DabPumpsLogin.ACCESS_TOKEN]):
            self._refresh_token = None
            self._refresh_expires_in = None
            self._refresh_expiry = None
            self._refresh_client_id = None
            self._refresh_client_secret = None

        # Do not clear login_method when called in a 'login' context, as it interferes with 
        # the loop iterating all login methods.
        if not context.startswith("login"):
            self._login_method = None
            self._login_time = None


    def _validate_token(self, token: str|None) -> str:
        try:
            jwt.decode(jwt=token, options={"verify_signature": False})
            return token
        except:            
            return ""


    def _validate_expires_in(self, expires_in: int|None, default: int) -> int:
        if expires_in:
            return expires_in
        else:
            return default


    def _calculate_expiry(self, expires_in: int) -> datetime:
        # Increase margin based on length of expires_in
        if   expires_in <       60*60: margin =       60  # expires_in up to 60 minutes leads to margin of 1 minute
        elif expires_in <    24*60*60: margin =    30*60  # expires_in up to 1 day leads to margin of 30 minutes
        elif expires_in < 10*24*60*60: margin = 12*60*60  # expires_in up to 10 days leads to margin of 12 hours
        else:                          margin = 24*60*60  # expires_in over 10 days leads to margin of 1 day

        return datetime.now() + timedelta(seconds=expires_in) - timedelta(seconds=margin)


    async def fetch_install_list(self):
        """
        Get installation list
        This fills:
          install_map    (details for each install)
        """

        # Retrieve data via REST request
        match self._fetch_method:
            case DabPumpsFetch.DABCS:    url = DABCS_API_URL + '/mobile/v1/installations'
            case DabPumpsFetch.DCONNECT: url = DCONNECT_API_URL + '/api/v1/installation' # or DABPUMPS_API_URL + '/getInstallationList'

        context = f"installations {self._username.lower()}"
        request = {
            "method": "GET",
            "url": url,
        }

        _LOGGER.debug(f"Retrieve installation list for '{self._username}' via {request["method"]} {request["url"]}")
        raw = await self._send_request(context, request)  

        # Process the resulting raw data
        # For DabCS:
        # {
        #   "installations": [
        #     { "name": "some_str", "installation_id": "some_guid", "metadata": { ... }, "current_user_role": "role", ... }
        #   ]
        # }
        # For DConnect:
        # {
        #   "values": [     # or "rows": [
        #     { "name": "some_str", "installation_id": "some_guid", "user_role": "role", ... }
        #   ]
        # }
        install_map = {}
        installations = raw.get('installations', None) or raw.get('values', None) or raw.get('rows', None) or []
        
        for install_idx, installation in enumerate(installations):
            
            install_id = installation.get('installation_id', '')
            install_name = installation.get('name', None) or installation.get('description', None) or f"installation {install_idx}"
            install_meta = installation.get('metadata', {})

            _LOGGER.debug(f"Installation found: {install_name}")
            install = DabPumpsInstall(
                id = install_id,
                name = install_name,
                description = installation.get('description', None) or '',
                company = installation.get('company', None) or install_meta.get('company', None) or '',
                address = installation.get('address', None) or install_meta.get('address', None) or '',
                role = installation.get('current_user_role', None) or installation.get('user_role', None) or DabPumpsUserRole.CUSTOMER,
                devices = len(installation.get('dums', None) or []),
            )
            install_map[install_id] = install

        # Sanity check. # Never overwrite a known install_map with empty lists
        if len(install_map)==0:
            raise DabPumpsDataError(f"No installations found in data")

        # Remember this data
        self._install_map_ts = datetime.now()
        self._install_map = install_map


    async def fetch_install_details(self, install_id: str):
        """
        Fetch all details from an installation.
        This fills:
          device_map    (details for each device)
          config_map    (config metadata for each device)
          status_map    (inital statuses for each device)
        """

        # Retrieve list of devices within this install
        raw = await self._fetch_install_devices(install_id)

        # First retrieve all device configs
        for config_id in [ d.config_id for d in self._device_map.values() if d.install_id==install_id ]:
            await self._fetch_device_config(config_id, raw_install_data=raw)

        # Next, generate static statuses from the device configs
        # and retrieve inital device statuses
        for serial in [ d.serial for d in self._device_map.values() if d.install_id==install_id ]:
            await self._fetch_static_statuses(serial)
            await self._fetch_device_statuses(serial, raw_install_data=raw)

            # Finally, derive extra device details
            await self._derive_device_details(serial)


    async def fetch_install_statuses(self, install_id: str):
        """
        Fetch the statuses for all devices in an installation
        This updates:
          status_map    (current statuses for each device)
        """

        match self._fetch_method:
            case DabPumpsFetch.DABCS:
                # Returns statuses for all devices in one call
                context = f"statuses {install_id}"
                request = { "method": "GET", "url": DABCS_API_URL + f"/mobile/v1/installations/{install_id}/dums" }
        
                _LOGGER.debug(f"Retrieve installation statuses via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)

            case DabPumpsFetch.DCONNECT:
                # Needs to retrieve data per device
                raw = None

        for serial in [ d.serial for d in self._device_map.values() if d.install_id==install_id ]:
            await self._fetch_device_statuses(serial, raw_install_data=raw)
        
        
    async def _fetch_install_devices(self, install_id: str):
        """Get installation details"""

        # Retrieve data via REST request
        match self._fetch_method:
            case DabPumpsFetch.DABCS:    url = DABCS_API_URL + f"/mobile/v1/installations/{install_id}/dums?include_configuration=true"
            case DabPumpsFetch.DCONNECT: url = DCONNECT_API_URL + f"/api/v1/installation/{install_id}" # or DABPUMPS_API_URL + f"/getInstallation/{install_id}"

        context = f"installation {install_id}"
        request = {
            "method": "GET",
            "url": url,
        }
        
        _LOGGER.debug(f"Retrieve installation details via {request["method"]} {request["url"]}")
        raw = await self._send_request(context, request)

        # Process the resulting raw data
        # For DabCS:
        # {
        #   "dums": [
        #     { "configuration_id": "guid3", "serial": "some_str", "status": { ... }, ... }
        #   ],
        #   "configurations": [
        #     { "guid": { "family": "str", "ProductName": "str", "params": [...], ... } }
        #   ]
        # }
        # For DConnect:
        # {
        #   "installation_id": "guid1",
        #   "dums": [
        #     { "configuration_id": "guid3", "serial": "some_str", ... }
        #   ]
        # }
        device_map = {}
        ins_dums = raw.get('dums', [])

        for dum_idx, dum in enumerate(ins_dums):
            dum_serial = dum.get('serial', None) or ''
            dum_name = dum.get('name', None) or dum.get('ProductName', None) or f"device {dum_idx}"
            dum_product = dum.get('ProductName', None) or dum.get('distro_embedded', None) or f"device {dum_idx}"
            dum_version = dum.get('configuration_name', None) or dum.get('distro_embedded', None) or ''
            dum_config = dum.get('configuration_id', None) or ''

            if not dum_serial: 
                raise DabPumpsDataError(f"Could not find installation attribute 'serial'")
            if not dum_config: 
                raise DabPumpsDataError(f"Could not find installation attribute 'configuration_id'")

            device = DabPumpsDevice(
                vendor = 'DAB Pumps',
                name = dum_name,
                id = self.create_id(dum_name),
                serial = dum_serial,
                product = dum_product,
                hw_version = dum_version,
                config_id = dum_config,
                install_id = install_id,
                # Attributes below are retrieved later on via fetch_device_details
                sw_version = None,
                mac_address = None,
            )
            device_map[dum_serial] = device
            
            _LOGGER.debug(f"Device found: {dum_name} with serial {dum_serial}")
            
        # Sanity check. # Never overwrite a known device_map
        if len(device_map) == 0:
            raise DabPumpsDataError(f"No devices found for installation id {install_id}")

        # Remember/update the found map.
        self._device_map_ts = datetime.now()
        self._device_map.update(device_map)

        # Cleanup devices from this installation that are no longer needed in _device_map
        candidate_list = [ k for k,v in self._device_map.items() if v.install_id == install_id and not k in device_map ]
        for key in candidate_list:
            self._device_map.pop(key, None)

        return raw


    async def _fetch_device_config(self, config_id: str, raw_install_data: dict|None = None):
        """Fetch the statuses for a DAB Pumps device, which then constitues the Sensors"""

        # Retrieve data via REST request
        conf = {}
        conf_id = None

        match self._fetch_method:
            case DabPumpsFetch.DABCS:
                if raw_install_data is None:
                    raise DabPumpsError("No raw install data was passed to function _fetch_device_config")

                # We have raw install data that includes all configurations; find the correct config
                # {
                #   "dums": [ ... ],
                #   "configurations": [
                #     { 
                #        "guid": { "family": "str", "ProductName": "str", "params": [...], ... } 
                #     }
                #   ]
                # }
                ins_configs = raw_install_data.get('configurations', [])

                for ins_config_id, ins_config in ins_configs.items():
                    if ins_config_id == config_id:
                        conf = ins_config
                        conf_id = ins_config_id
                        break

            case DabPumpsFetch.DCONNECT: 
                raw_install_data = None

                context = f"configuration {config_id}"
                request = { "method": "GET", "url":  DCONNECT_API_URL + f"/api/v1/configuration/{config_id}" }
        
                _LOGGER.debug(f"Retrieve device config for '{config_id}' via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)

                # {
                #    "configuration_id": "id", "name": "some_name", "label": "some_str", "description": "some_str", "metadata": { ... }, ... }
                # }
                conf = raw
                conf_id = None

        # Process the resulting raw data
        config_map = {}

        conf_id = conf_id or conf.get('configuration_id', '')
        conf_name = conf.get('name') or conf.get('ProductName') or f"config {conf_id}"
        conf_label = conf.get('label') or conf.get('family') or f"config {conf_id}"
        conf_descr = conf.get('description') or conf.get('ProductName') or f"config {conf_id}"
        conf_params = {}

        if conf_id != config_id: 
            raise DabPumpsDataError(f"Expected configuration id {config_id} was not found in returned configuration data")
            
        meta = conf.get('metadata') or {}
        meta_params = meta.get('params') or conf.get('params') or []
        
        for meta_param_idx, meta_param in enumerate(meta_params):
            # get param details
            param_name = meta_param.get('name') or f"param{meta_param_idx}"
            param_type = meta_param.get('type') or ''
            param_unit = meta_param.get('unit')
            param_weight = meta_param.get('weight')
            param_min = meta_param.get('min') or meta_param.get('warn_low')
            param_max = meta_param.get('max') or meta_param.get('warn_hi')
            param_family = meta_param.get('family') or ''
            param_group = meta_param.get('group') or ''
            
            values = meta_param.get('values') or []
            param_values = { str(v[0]): str(v[1]) for v in values if len(v) >= 2 }
            
            param = DabPumpsParams(
                key = param_name,
                name = self._translate_string(param_name),
                type = param_type,
                unit = param_unit,
                weight = param_weight,
                values = param_values,
                min = param_min,
                max = param_max,
                family = param_family,
                group = param_group,
                view = ''.join([ s[0] for s in (meta_param.get('view') or []) ]),
                change = ''.join([ s[0] for s in (meta_param.get('change') or []) ]),
                log = ''.join([ s[0] for s in (meta_param.get('log') or []) ]),
                report = ''.join([ s[0] for s in (meta_param.get('report') or []) ])
            )
            conf_params[param_name] = param
        
        config = DabPumpsConfig(
            id = conf_id,
            label = conf_label,
            description = conf_descr,
            meta_params = conf_params
        )
        config_map[conf_id] = config
        
        if len(config_map) == 0:
            raise DabPumpsDataError(f"No config found for '{config_id}'")
        
        _LOGGER.debug(f"Configuration found: {conf_name} with {len(conf_params)} metadata params")        

        # Merge with configurations from other devices
        self._config_map_ts = datetime.now()
        self._config_map.update(config_map)
        

    async def _fetch_static_statuses(self, serial: str):
        """Fetch the static statuses for a DAB Pumps device"""

        # Process the existing data
        status_map = {}

        device = self._device_map.get(serial, None)
        if not device:
            return

        config = self._config_map.get(device.config_id)
        if not config or not config.meta_params:
            return

        for params in config.meta_params.values():
            is_static = False
            code = None
            value = ""

            # Detect known params that are normally hidden until an action occurs
            if params.key in DEVICE_STATUS_STATIC:
                is_static = True
                code = None
                value = None

            # Detect 'button' params (type 'enum' with only one possible value)
            if params.type == DabPumpsParamType.ENUM and len(params.values or []) == 1:
                is_static = True
                code = str(params.min) if params.min is not None else "0"
                value = ""

            # Add other static params types here in future
            pass

            if is_static:
                status_key = AsyncDabPumps.create_id(device.serial, params.key)
                status_new = DabPumpsStatus(
                    serial = device.serial,
                    key = params.key,
                    name = self._translate_string(params.key),
                    code = code,
                    value = value,
                    unit = params.unit,
                    status_ts = datetime.now(timezone.utc),
                    update_ts = None,
                )
                status_map[status_key] = status_new 

        # Merge with statuses from other devices
        self._status_static_map_ts = datetime.now()
        self._status_static_map.update(status_map)
        
        
    async def _fetch_device_statuses(self, serial: str, raw_install_data: dict|None = None):
        """Fetch the statuses for a DAB Pumps device"""

        statusts = ""
        values = {}

        match self._fetch_method:
            case DabPumpsFetch.DABCS:
                if raw_install_data is None:
                    raise DabPumpsError("No raw install data was passed to function _fetch_device_statuses")
            
                # We have raw install data that includes all devices; find the correct device
                # {
                #   "dums": [
                #     { "configuration_id": "guid3", "serial": "some_str", "statusts": "some_data", "status": { ... }, ... }
                #   ]
                # }
                ins_dums = raw_install_data.get('dums', [])
            
                for dum in ins_dums:
                    dum_serial = dum.get('serial', None) or ''
                    if dum_serial == serial:
                        statusts = dum.get('statusts') or ""
                        values = dum.get('status') or {}
                        break
        
            case DabPumpsFetch.DCONNECT: 
                # Raw install data does not contain statuses when using this method.
                # Retrieve statuses specific for this device
                context = f"statuses {serial}"
                request = { "method": "GET", "url": DCONNECT_API_URL + f"/dumstate/{serial}" } # or f"/api/v1/dum/{serial}/state"
                
                _LOGGER.debug(f"Retrieve device statuses for '{serial}' via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)
                
                # {
                #   "statusts": "some_datetime",
                #   "status": "{ "key1": "value1", "key2": "value2", ... }",   as string!
                #   ...
                # }
                statusts = raw.get('statusts') or ""
                status = raw.get('status') or "{}" # string!
                values = json.loads(status)

        # Process the resulting raw data
        status_map = {}
        status_ts = datetime.fromisoformat(statusts) if statusts else datetime.now(timezone.utc)

        for item_key, item_code in values.items():
            try:
                # the code 'h' is used when a property is not available/supported
                # Note the some properties (PowerShowerCountdown, SleepModeCountdown) can switch between 
                # availabe (and be in _status_actual_map) and unavailable (still be in _status_static_map).
                if item_code=='h':
                    continue

                # Check if this status was recently updated via change_device_status
                # We keep the updated value for a hold period to prevent it from flipping back and forth 
                # between its old value and new value because of delays in update on the DAB server side.
                status_key = AsyncDabPumps.create_id(serial, item_key)
                status_old = self._status_actual_map.get(status_key, None)

                if status_old and status_old.update_ts is not None and \
                (datetime.now(timezone.utc) - status_old.update_ts).total_seconds() < STATUS_UPDATE_HOLD:

                    _LOGGER.info(f"Skip refresh of recently updated status ({status_key})")
                    status_map[status_key] = status_old
                    continue

                # Resolve the coded value into the real world value
                (item_val, item_unit) = self._decode_status_value(serial, item_key, item_code)

                # Add it to our statuses
                status_new = DabPumpsStatus(
                    serial = serial,
                    key = item_key,
                    name = self._translate_string(item_key),
                    code = item_code,
                    value = item_val,
                    unit = item_unit,
                    status_ts = status_ts,
                    update_ts = None,
                )
                status_map[status_key] = status_new

            except Exception as e:
                _LOGGER.warning(f"Exception while processing status for '{serial}:{item_key}': {e}")

        if len(status_map) == 0:
            raise DabPumpsDataError(f"No statuses found for '{serial}'")
        
        _LOGGER.debug(f"Statuses found for '{serial}' with {len(status_map)} values")

        # Merge with statuses from other devices
        self._status_actual_map_ts = datetime.now()
        self._status_actual_map.update(status_map)

        # Cleanup statuses from this device that are no longer needed in _status_actual_map
        candidate_map = { k:v for k,v in self._status_actual_map.items() if v.serial == serial and not k in status_map }

        for status_key, status_old in candidate_map.items():
                
            # Check if this status was recently updated via change_device_status
            # We keep the updated value for a hold period to prevent it from flipping back and forth 
            # between its old value and new value because of delays in update on the DAB server side.
            if status_old.update_ts is not None and \
               (datetime.now(timezone.utc) - status_old.update_ts).total_seconds() < STATUS_UPDATE_HOLD:

                # Recently updated static status (i.e. button press)
                continue
                
            # Status can be removed
            self._status_actual_map.pop(status_key, None)
        
        
    async def _derive_device_details(self, serial: str):
        """
        Derive extra details for a DAB Pumps device

        This function should be run AFTER both _fetch_device_config and _fetch_device_statuses
        """
    
        device = self._device_map[serial]

        # Search for specific statuses
        for attr,keys in DEVICE_ATTR_EXTRA.items():
            for key in keys:

                # Try to find a status for this key and device
                status = next( (status for status in self._status_actual_map.values() if status.serial==serial and status.key==key), None)
                
                if status is not None and status.value is not None:
                    # Found it. Update the device attribute (workaround via dict because it is a namedtuple)
                    if getattr(device, attr) != status.value:
                        _LOGGER.debug(f"Found extra device attribute {serial} {attr} = {status.value}")
                        setattr(device, attr, status.value)

        self._device_detail_ts = datetime.now()


    async def change_device_status(self, serial: str, key: str, code: str|None=None, value: Any|None=None):
        """
        Set a new status value for a DAB Pumps device.

        Either code (the value as expected by Dab Pumps backend) or value (the real world value)
        needs to be supplied.
        """

        # Sanity check
        if code is None and value is None:
            
            _LOGGER.warning(f"To change device status either 'code' or 'value' needs to be specified")
            return False
        
        status_key = AsyncDabPumps.create_id(serial, key)  

        status = self._status_actual_map.get(status_key, None) or self._status_static_map.get(status_key, None)
        if not status:
            # Not found
            return False
        
        # If needed encode the value into what DabPumps backend expects
        if code is None:
            code = self._encode_status_value(serial, key, value)
        else:
            (value,_) = self._decode_status_value(serial, key, code)
            
        if status.code == code:
            # Not changed
            return False
        
        _LOGGER.info(f"Set {serial}:{key} from {status.value} to {value} ({code})")
        
        # update the cached value in status_map
        status_upd = replace(status, code = code, value = value, update_ts = datetime.now(timezone.utc))
        self._status_actual_map[status_key] = status_upd
        
        # Update data via REST request
        context = f"set {status_upd.serial}:{status_upd.key}"

        match self._fetch_method:
            case DabPumpsFetch.DABCS: url = DABCS_API_URL + f"/mobile/v1/dums/{status_upd.serial}/setparam?skipLogging=false"
            case DabPumpsFetch.DCONNECT: url = DCONNECT_API_URL + f"/dum/{status_upd.serial}"
        
        request = {
            "method": "POST",
            "url": url,
            "headers": {
                'Content-Type': 'application/json',
            },
            "json": {
                'key': status_upd.key, 
                'value': status_upd.code
            },
        }
        
        _LOGGER.debug(f"Set device param for '{status.serial}:{status.key}' to '{value}' via {request["method"]} {request["url"]}")
        raw = await self._send_request(context, request)
        
        # If no exception was thrown then the operation was successfull
        return True
    

    async def change_install_role(self, install_id: str, role_old: DabPumpsUserRole, role_new: DabPumpsUserRole):
        """
        Set a new role for the logged in user within a DAB Pumps install.
        """

        match self._fetch_method:
            case DabPumpsFetch.DABCS: 
                # Delete old role then add new role
                context = f"del {install_id}:{self._username}"
                request = {
                    "method": "DELETE",
                    "url": DABCS_API_URL + f"/mobile/v1/installations/{install_id}/users/{role_old}/{self._username}",
                }
                _LOGGER.debug(f"Del install role via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)

                context = f"add {install_id}:{self._username}"
                request = {
                    "method": "POST",
                    "url": DABCS_API_URL + f"/mobile/v1/installations/{install_id}/users/{role_new}/{self._username}",
                    "headers": {
                      'Content-Length': '0',
                    },
                }
                _LOGGER.debug(f"Add install role via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)

            case DabPumpsFetch.DCONNECT: 
                # Get user_id from username
                context = f"user {self._username}"
                request = {
                    "method": "GET",
                    "url": DCONNECT_API_URL + f"/api/v1/user", # or DCONNECT_API_URL + f"/user/{username}/search"
                }
                _LOGGER.debug(f"Get user via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)

                user_id = raw.get('user_id') or ""

                # Delete old role then add new role
                context = f"del {install_id}:{self._username}"
                request = {
                    "method": "GET",
                    "url": DCONNECT_API_URL + f"/installation/{install_id}/remove/{role_old}/{user_id}",
                }
                _LOGGER.debug(f"Del install role via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)

                context = f"add {install_id}:{self._username}"
                request = {
                    "method": "GET",
                    "url": DCONNECT_API_URL + f"/installation/{install_id}/add/{role_new}/{user_id}",
                }
                _LOGGER.debug(f"Add install role via {request["method"]} {request["url"]}")
                raw = await self._send_request(context, request)
        
        # If no exception was thrown then the operation was successfull
        return True


    async def fetch_strings(self, lang: str):
        """Get string translations"""
    
        # Retrieve data via REST request
        context = f"localization_{lang}"
        request = {
            "method": "GET",
            "url": DCONNECT_API_URL + f"/resources/js/localization_{lang}.properties?format=JSON&fullmerge=1",
            "flags": {
                'authorize': False,
            },
        }
        
        _LOGGER.debug(f"Retrieve language info via {request["method"]} {request["url"]}")
        raw = await self._send_request(context, request)

        # Process the resulting raw data
        # For DConnect:
        # {
        #   "bundle": "2 letter language code",
        #   "messages": {
        #     "key1": "value1", "key2": "value2", ...
        #   },
        #   ...
        # }
        language = raw.get('bundle', '')
        messages = raw.get('messages', {})
        string_map = { k: v for k, v in messages.items() }
        
        # Sanity check. # Never overwrite a known string_map with empty lists
        if len(string_map) == 0:
            raise DabPumpsDataError(f"No strings found in data")

        _LOGGER.debug(f"Strings found: {len(string_map)} in language '{language}'")
        
        # Remember this data
        self._string_map_ts = datetime.now() if len(string_map) > 0 else datetime.min
        self._string_map_lang = language
        self._string_map = string_map


    def get_status_value(self, serial: str, key: str) -> DabPumpsStatus:
        """
        Resolve code, value and unit for a status
        """
        status_key = AsyncDabPumps.create_id(serial, key)

        # Return status for this key; decoding and translation of code into value is already done.
        return self._status_actual_map.get(status_key, None) or self._status_static_map.get(status_key, None)


    def get_status_metadata(self, serial: str, key: str, translate:bool = True) -> DabPumpsParams:
        """
        Resolve meta params for a status
        """

        # Find the meta params for this status
        device = self._device_map.get(serial, None) if self._device_map else None
        config = self._config_map.get(device.config_id, None) if device is not None and self._config_map  else None
        params = config.meta_params.get(key, None) if config is not None and config.meta_params else None

        # Apply translations
        if translate and params is not None and params.values is not None:
            params = replace(params, values = { k:self._translate_string(v) for k,v in params.values.items() })

        return params


    def _decode_status_value(self, serial: str, key: str, code: str) -> Any:
        """
        Resolve the coded value into the real world value.
        Also returns the unit of measurement.
        """

        # Find the meta params for this status
        params = self.get_status_metadata(serial, key, translate=False)

        if params is None or code is None:
            return (code, '')
        
        # param:DabPumpsParams - 'key, type, unit, weight, values, min, max, family, group, view, change, log, report'
        match params.type:
            case DabPumpsParamType.ENUM:
                # Lookup value and translate
                value = self._translate_string(params.values.get(code, code))

            case DabPumpsParamType.MEASURE:
                if code != '':
                    if params.weight and params.weight != 1 and params.weight != 0:
                        # Convert to float
                        precision = int(math.floor(math.log10(1.0 / params.weight)))
                        value = round(float(code) * params.weight, precision)
                    else:
                        # Convert to int
                        value = int(code)
                else:
                    value = None
                    
            case DabPumpsParamType.LABEL:
                # Convert to string; no translation
                value = str(code)

            case _:
                _LOGGER.warning(f"Encountered an unknown params type '{params.type}' for '{serial}:{params.key}'. Please contact the integration developer to have this resolved.")
                value = None

        return (value, params.unit)


    def _encode_status_value(self, serial: str, key: str, value: Any) -> Any:
        """
        Resolve the real world value into the coded value.
        """

        # Find the meta params for this status
        device = self._device_map.get(serial, None) if self._device_map else None
        config = self._config_map.get(device.config_id, None) if device is not None and self._config_map  else None
        params = config.meta_params.get(key, None) if config is not None and config.meta_params else None

        if params is None or value is None:
            return str(value)
        
        # param:DabPumpsParams - 'key, type, unit, weight, values, min, max, family, group, view, change, log, report'
        match params.type:
            case DabPumpsParamType.ENUM:
                code = next( (str(k) for k,v in params.values.items() if v==value), None)
                if code is None:
                    code = str(value)

            case DabPumpsParamType.MEASURE:
                if params.weight and params.weight != 1 and params.weight != 0:
                    # Convert from float to int
                    code = str(int(round(value / params.weight)))
                else:
                    # Convert to int
                    code = str(int(value))
                    
            case DabPumpsParamType.LABEL:
                # Convert to string
                code = str(value)

            case _:
                _LOGGER.warning(f"Encountered an unknown params type '{params.type}' for '{serial}:{params.key}'. Please contact the integration developer to have this resolved.")
                code = None
        
        return code
    

    def _translate_string(self, str: str) -> str:
        """
        Return 'translated' string or original string if not found
        """
        return self._string_map.get(str, str) if self._string_map else str
    

    async def _send_request(self, context, request):
        """GET or POST a request for JSON data"""

        timestamp = datetime.now()
        flags = request.get("flags", {})
        flags_redirects = flags.get("redirects", True)
        flags_authorize = flags.get("authorize", True)

        # Always add certain headers
        if not "headers" in request:
            request["headers"] = {}

        if self._auth_method == DabPumpsAuth.HEADER and self._access_token and not context.startswith('login') and flags_authorize:
            request["headers"]['Authorization'] = 'Bearer ' + self._access_token

        if self._extra_headers:
            request["headers"].update(self._extra_headers)

        # Add some default headers if not already set via extra_headers
        request["headers"].setdefault('User-Agent', 'python-requests/2.20.0')
        request["headers"].setdefault('Cache-Control', 'no-store, no-cache, max-age=0')
        request["headers"].setdefault('Connection', 'close')

        # Perform the request
        try:
            req = self._http_client.build_request(
                method = request["method"],
                url = request["url"],
                params = request.get("params", None), 
                data = request.get("data", None),
                json = request.get("json", None),
                headers = request.get("headers", None),
                timeout = httpx.Timeout(HTTPX_REQUEST_TIMEOUT),
            )
            rsp = await self._http_client.send(req, follow_redirects=flags_redirects)

            # Remember actual requests and response params, used for diagnostics
            _LOGGER.debug(f"rsp: {rsp}")

            request["headers"] = req.headers
            response = {
                "success": rsp.is_success or rsp.is_redirect,
                "status": f"{rsp.status_code} {rsp.reason_phrase}",
                "headers": rsp.headers,
                "elapsed": (datetime.now() - timestamp).total_seconds(),
            }
            if rsp.is_success and rsp.headers.get('content-type','').startswith('application/json'):
                response["json"] = rsp.json()
            else:
                response["text"] = rsp.text
            
        except Exception as ex:
            error = f"Unable to perform request, got exception '{str(ex)}' while trying to reach {request["url"]}"
            _LOGGER.debug(error)

            if flags_authorize:
                # Force a logout to so next login will be a real login, not a token reuse
                await self._logout(context)
                
            raise DabPumpsConnectError(error)

        # Save the diagnostics if requested
        await self._update_diagnostics(timestamp, context, request, response)
        
        # Check response
        if not response["success"]:
            error = f"Unable to perform request, got response {response["status"]} while trying to reach {request["url"]}"
            _LOGGER.debug(error)

            # Force a logout to so next login will be a real login, not a token reuse
            await self._logout(context)
            if "401" in response["status"]:
                raise DabPumpsAuthError(error)
            else:
                raise DabPumpsConnectError(error)
        
        if flags.get("redirects",None) == False and response['status'].startswith("302"):
            return response["headers"].get("location", '')

        elif "text" in response:
            return response["text"]
        
        elif "json" in response:
            # if the result structure contains a 'res' value, then check it
            json = response["json"]
            res = json.get('res', None)
            if res and res != 'OK':
                # BAD RESPONSE: { "res": "ERROR", "code": "FORBIDDEN", "msg": "Forbidden operation", "where": "ROUTE RULE" }
                code = json.get('code', '')
                msg = json.get('msg', '')
                
                if code.upper() in ['FORBIDDEN', 'WRONGCREDENTIAL']:
                    error = f"Authorization failed: {res} {code} {msg}"
                    _LOGGER.debug(error)

                    # Force a logout to so next login will be a real login, not a token reuse
                    await self._logout(context)
                    raise DabPumpsAuthError(error)
                else:
                    error = f"Unable to perform request, got response {res} {code} {msg} while trying to reach {request["url"]}"
                    _LOGGER.debug(error)
                    raise DabPumpsError(error)

            return json
        
        else:
            return None
    

    async def _update_diagnostics(self, timestamp: datetime, context: str, request: dict|None, response: dict|None, token: dict|None = None):

        if self._diagnostics_callback:
            item = DabPumpsHistoryItem.create(timestamp, context, request, response, token)
            detail = DabPumpsHistoryDetail.create(timestamp, context, request, response, token)
            data = {
                "login_time": self._login_time,
                "login_method": self._login_method,
                "fetch_method": self._fetch_method,
                "auth_method": self._auth_method,
                "extra_headers": self._extra_headers,

                "access_token": self._access_token,
                "access_expires_in": self._access_expires_in,
                "access_expiry": self._access_expiry,
                "refresh_token": self._refresh_token,
                "refresh_expires_in": self._refresh_expires_in,
                "refresh_expiry": self._refresh_expiry,
                "refresh_client_id": self._refresh_client_id,
                "refresh_client_secret": self._refresh_client_secret,

                "string_map_lang": self.string_map_lang,
            }

            self._diagnostics_callback(context, item, detail, data)
    

