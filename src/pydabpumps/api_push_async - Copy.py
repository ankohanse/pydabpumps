"""api_push.py: DabPumps API for DAB Pumps integration."""

import asyncio
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

import autobahn.asyncio.wamp as asyncio_wamp
import autobahn.wamp as wamp
import autobahn.wamp.component as wamp_component
import autobahn.wamp.types as wamp_types

from autobahn.asyncio.websocket import WebSocketClientProtocol
from autobahn.asyncio.websocket import WebSocketClientFactory

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
    H2D_APP_REDIRECT_URI,
    H2D_APP_CLIENT_ID,
    H2D_APP_CLIENT_SECRET,
    DCONNECT_APP_CLIENT_ID,
    DCONNECT_APP_CLIENT_SECRET,
    DCONNECT_APP_USER_AGENT,
    STATUS_UPDATE_HOLD,
    HTTPX_REQUEST_TIMEOUT,
    utcnow,
    utcmin,
)

from .api_async import(
    AsyncDabPumps,
)
from .const import (
    WAMP_URL,
    WAMP_REALM,
    WAMP_AUTH_METHODS,
    WAMP_AUTH_ID,
)
from .data import (
    DabPumpsError,
    DabPumpsConnectError,
    DabPumpsAuthError,
    DabPumpsDataError,
    DabPumpsStatusCode,
    DabPumpsUserRole,
    DabPumpsParamType,
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsDeviceConfig,
    DabPumpsDeviceState,
    DabPumpsParams,
    DabPumpsStatus,
    DabPumpsLogin,
    DabPumpsFetch,
    DabPumpsAuth,
    DabPumpsLoginInfo,
    DabPumpsAccessTokenInfo,
    DabPumpsRefreshTokenInfo,
    DabPumpsSessionInfo,
    DabPumpsHistoryItem,
    DabPumpsHistoryDetail,
)

_LOGGER = logging.getLogger(__name__)


class AsyncDabPumpsPush(AsyncDabPumps):
    
    def __init__(self, username, password, client:httpx.AsyncClient=None, login_info:DabPumpsLoginInfo=None, access_token_info:DabPumpsAccessTokenInfo=None, refresh_token_info:DabPumpsRefreshTokenInfo=None):
        super().__init__(
            username = username, 
            password = password, 
            client = client,
            login_info = login_info, 
            access_token_info = access_token_info, 
            refresh_token_info = refresh_token_info
        )
        
        # Init Wamp
        self._wamp_runner = asyncio_wamp.ApplicationRunner(url = WAMP_URL, realm = WAMP_REALM)
        self._wamp_runner_started = False


    async def login(self, test_method:DabPumpsLogin=None):
        """
        Login to DAB Pumps by trying each of the possible login methods.
        Guards for calls from multiple threads.
        """

        # Start the Http login first
        await super().login()

        # Start a new session if needed
        session_started = await super()._start_session()
        
        # Start Wamp (Websocket) handler
        if session_started and not self._wamp_runner_started:
            factory = WebSocketClientFactory(WAMP_URL)
            factory.protocol = AsyncDabPumpsPushProtocol
            factory.protocols = ['wamp.2.json']

            loop = asyncio.get_event_loop()
            transport, proto = await loop.create_connection(factory, host="dconnect.dabpumps.com", port=443, ssl=True)
            self._wamp_runner_started = True


    async def logout(self):
        """Logout from DAB Pumps"""

        # Stop Wamp (Websocket) handler
        if self._wamp_runner_started:
            self._wamp_runner.stop()

        # Stop the session
        await super()._stop_session()

        # Stop the Http sessions
        await super().logout()


# DabPumps push session via Wamp
class AsyncDabPumpsPushProtocol(WebSocketClientProtocol):
    
    def __init__(self):  #, config: wamp_types.ComponentConfig, api_instance: AsyncDabPumpsPush):
        super().__init__()
        #super().__init__(config)
        #self._api = api_instance


    def onOpen(self):
        _LOGGER.debug(f"H2D socket open")
        hello_msg = [
            1, 
            WAMP_REALM,
            {
                "agent": "Wampy.js v7.1.1",
                "roles": {
                "publisher": {
                    "features": {
                    "subscriber_blackwhite_listing": True,
                    "publisher_exclusion": True,
                    "publisher_identification": True,
                    "payload_passthru_mode": True
                    }
                },
                "subscriber": {
                    "features": {
                    "pattern_based_subscription": True,
                    "publication_trustlevels": True,
                    "publisher_identification": True,
                    "payload_passthru_mode": True
                    }
                },
                "caller": {
                    "features": {
                    "caller_identification": True,
                    "progressive_call_results": True,
                    "call_canceling": True,
                    "call_timeout": True,
                    "payload_passthru_mode": True
                    }
                },
                "callee": {
                    "features": {
                    "caller_identification": True,
                    "call_trustlevels": True,
                    "pattern_based_registration": True,
                    "shared_registration": True,
                    "payload_passthru_mode": True
                    }
                }
                },
                "authid": "iopapp",
                "authmethods": ["ticket"],
                "authextra": {}
            }
        ]            
        hello_str = json.dumps(hello_msg)
        hello_bin = hello_str.encode()
        self.sendMessage(hello_bin)


    def onMessage(self, payload, isBinary):
        if isBinary:
            _LOGGER.debug(f"Binary message received: {len(payload)}")
        else:
            _LOGGER.debug(f"Text message received: {payload.decode('utf8')}")


    async def onChallenge(self, challenge: wamp_types.Challenge):
        """
        Handle the challenge send back by the H2D Wamp router
        """
        _LOGGER.debug(f"H2D Wamp session challenge received. Challenge: {challenge}")

        match challenge.method:
            case 'ticket': return self._session_info.wstoken
            case _: raise DabPumpsAuthError(f"Unexpected method '{challenge.method} in Challenge received from H2D Wamp server")


    async def onJoin(self, details: wamp.SessionDetails):
        _LOGGER.debug(f"H2D Wamp session authenticated and joined. Details: {details}")


    def onDisconnect(self):
        _LOGGER.debug(f"H2D Wamp session disconnect")

        asyncio.get_event_loop().stop()
        self._wamp_runner_started = False


