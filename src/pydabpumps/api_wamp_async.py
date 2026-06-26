"""
api.py: DabPumps API for DAB Pumps integration.

The Api can either be used to retrieve data from the DAB Pumps servers via polling,
but also provides functionality to subscribe to push data.
"""

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

from autobahn.asyncio.wamp import ApplicationRunner, ApplicationSession
from autobahn.wamp import ComponentConfig, EventDetails, SessionDetails, SubscribeOptions
from autobahn.wamp.types import Challenge, Subscription

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, parse_qs


from .api_base_async import(
    AsyncDabPumpsBase,
)
from .const import (
    WAMP_URL,
    WAMP_REALM,
    WAMP_AUTH_METHODS,
    WAMP_AUTH_ID,
    utcnow,
    utcmin,
)
from .data import (
    DabPumpsAuthError,
    DabPumpsDeviceState,
    DabPumpsStatus,
    DabPumpsLogin,
    DabPumpsLoginInfo,
    DabPumpsAccessTokenInfo,
    DabPumpsRefreshTokenInfo,
)

_LOGGER = logging.getLogger(__name__)


class WampMethod(StrEnum):
    SUBSCRIBE = 'WampSubscribe'
    SUBSCRIBED = 'WampSubscribed'
    EVENT = 'WampEvent'


class WampSubscriptionType(StrEnum):
    DEVICE_STATE = 'DeviceState'


@dataclass
class WampSubscriptionDetails:
    context: str = None
    request: dict = None
    response: dict = None
    callback: Any = None


class AsyncDabPumps(AsyncDabPumpsBase):
    
    def __init__(self, username, password, client:httpx.AsyncClient=None, login_info:DabPumpsLoginInfo=None, access_token_info:DabPumpsAccessTokenInfo=None, refresh_token_info:DabPumpsRefreshTokenInfo=None):
        super().__init__(
            username = username, 
            password = password, 
            client = client,
            login_info = login_info, 
            access_token_info = access_token_info, 
            refresh_token_info = refresh_token_info
        )
        
        # Wamp session
        self._wamp_runner = ApplicationRunner(url = WAMP_URL, realm = WAMP_REALM)
        self._wamp_runner_started = asyncio.Event()
        self._wamp_session = None
        self._wamp_session_started = asyncio.Event()
        self._wamp_subscription_map: dict[str, WampSubscriptionDetails] = {}    # topic -> { context, request, response, callback }


    async def login(self, test_method:DabPumpsLogin=None):
        """
        Login to DAB Pumps by trying each of the possible login methods.
        Guards for calls from multiple threads.

        Also makes sure that the Wamp/Push connection is restored if is was previously used
        """

        # Login via Http
        await super().login(test_method)

        # if needed, start the user session and Wamp session
        if self._wamp_subscription_map:
            await self._start_user_session()
            await self._start_wamp_session()


    async def close(self):
        """Safely logout and close all client handles"""

        # Stop Wamp session and user session
        await self._stop_wamp_session()
        await self._stop_user_session()

        # Finally, logout and close http client
        await super().close()


    async def on_device_state(self, serial: str, callback) -> bool:
        """
        Subscribe to status changes for a device.

        Callback must function in form of:
            async def fn(serial: str, state: DabPumpsDeviceState)

        The passed state only contains the updated statuses. 
        To get all statuses ignore the state param and instead call:
            state = api.device_state_map.get(serial)
        """

        # Determine the topic for this device
        device = self._device_map.get(serial)
        if device is None: 
            return False
        
        await self._wamp_subscribe_request(
            context = f"subscribe device {serial}",
            request = {
                'method': WampMethod.SUBSCRIBE,
                'type': WampSubscriptionType.DEVICE_STATE,
                'topic': f"dabcs.iop.{device.install_id}.dums.{device.id}",
                'device_serial': serial,
            },
            callback = callback,
        )


    async def _start_wamp_session(self) -> bool:
        """
        Start Wamp/push handler
        """
        if not self._session_info.wstoken:
            return False    # requirements not met

        if self._wamp_runner_started.is_set():
            return True     # Already started
        
        try:
            await self._wamp_runner.run(make=self._wamp_session_factory, start_loop=False)
            self._wamp_runner_started.set()
            return True

        except Exception as e:
            _LOGGER.debug(f"Unable to start Wamp session, got exception '{str(e)}'")
            return False


    async def _stop_wamp_session(self):
        """
        Stop Wamp/push handler
        """
        if self._wamp_session_started.is_set():
            self._wamp_session.leave()
            self._wamp_session.disconnect()
            self._wamp_session_started.clear()

        if self._wamp_runner_started.is_set():
            # Don't call stop(); it throws a 'not implemented' exception
            # self._wamp_runner.stop()
            self._wamp_runner_started.clear()


    def _wamp_session_factory(self, config):
        """
        Factory to create an Wamp session object
        """
        self._wamp_session = AsyncDabPumpsWampSession(config, api_instance=self)

        _LOGGER.debug(f"Wamp session created")
        return self._wamp_session
    

    async def _wamp_subscribe_cancelled(self):
        """
        Flag any previous wamp requests as cancelled so that they can be resubmitted in a next session
        """
        subs = [sub for sub in self._wamp_subscription_map.values() if sub.response is not None]
        if subs:
            _LOGGER.debug(f"Wamp subscribe cancelled")
            for sub in subs:
                sub.response = None


    async def _wamp_subscribe_resubmit(self):
        """
        Resubmitted any previous or pending subscribe requests
        """
        subs = [sub for sub in self._wamp_subscription_map.values() if sub.response is None]
        if subs:
            _LOGGER.debug(f"Wamp subscribe resubmit")
            for sub in subs:
                await self._wamp_subscribe_request(sub.context, sub.request, sub.callback)
        

    async def _wamp_subscribe_request(self, context: str, request: dict, callback=None):
        """
        Subscribe to a Wamp/push topic
        """

        # If needed, trigger start of the user session and the Wamp (Websocket) handler
        await self._start_user_session()
        await self._start_wamp_session()
        
        serial = request['device_serial']
        topic = request['topic']
        _LOGGER.info(f"Subscribe to changes for device '{serial}' via topic '{topic}'")

        # Perform the request
        timestamp = utcnow()
        response = {}
        try:
            # Remember this subscription request in case we need to reconnect later
            self._wamp_subscription_map[topic] = WampSubscriptionDetails(context=context, request=request, response=None, callback=callback)

            # If session is not (yet) joined then we're done. Wamp request will be triggered once (re-)joined
            if not self._wamp_session_started.is_set():
                return True
            
            # Subscribe now
            subscription: Subscription = await self._wamp_session.subscribe(
                handler = self._wamp_session.onEvent, 
                topic = topic, 
                options = SubscribeOptions(match="exact", details=True)
            )

            # Flag this subscription request as subscribed
            response = {
                'method': WampMethod.SUBSCRIBED,
                'subscription_id': subscription.id,
                'elapsed': round((utcnow() - timestamp).total_seconds(), 1),
            }
            self._wamp_subscription_map[topic].response = response

            # Save the diagnostics if requested
            await self._update_diagnostics(timestamp, context, request, response)
            return True

        except Exception as e:
            error = f"Unable to perform subscribe request, got exception '{str(e)}' while trying to reach {request['method']} '{request['topic']}'"
            _LOGGER.debug(error)
            return False


    async def _wamp_event_handler(self, topic: str, data: Any):
        """
        handle wamp/push data received from the DAB Pumps servers
        """
        info = self._wamp_subscription_map.get(topic)
        if info is None:
            return
        
        request = info.request
        
        match request['type']:
            case WampSubscriptionType.DEVICE_STATE:
                serial = request['device_serial']

                # Save the diagnostics if requested
                timestamp = utcnow()
                context = f"event for device {serial}"
                response = {
                    'method': WampMethod.EVENT,
                    'type': WampSubscriptionType.DEVICE_STATE,
                    'topic': topic,
                    'device_serial': serial,
                    'json': data,
                }
                await self._update_diagnostics(timestamp, context, None, response)

                # {
                #   "status": {
                #      "HO_PowerOnHours": "76008",
                #      "MainLoopTime": "1418"
                #   },
                #   "statusts": 1781583879599
                # }
                statusts = data.get('statusts') or None
                values = data.get('status') or {}

                _LOGGER.debug(f"Received {len(values)} new statuses for device {serial}")

                # Merge with existing statuses for this device
                state_new = self._parse_device_state(serial, statusts, None, values)
                state_old = self._device_state_map.get(serial) or DabPumpsDeviceState()

                self._device_state_map[serial] = DabPumpsDeviceState(
                    status_ts = max(state_old.status_ts, state_new.status_ts),
                    status = state_old.status | state_new.status,
                )

                # Notify our parent via the callback that was provided earlier
                if info.callback is not None:
                    try:
                        await info.callback(serial, state_new)

                    except Exception as e:
                        _LOGGER.debug(f"Exception while calling callback: {str(e)}")


            case _:
                _LOGGER.warning(f"Encountered an unknown subscription type '{info.type}'. Please contact the integration developer to have this resolved.")
                return



class AsyncDabPumpsWampSession(ApplicationSession):
    """
    DabPumps socket push session via Wamp
    """
    
    def __init__(self, config: ComponentConfig, api_instance: AsyncDabPumps):
        """
        Create an instance of the Wamp ApplicationSession
        """
        super().__init__(config)
        self._api = api_instance


    async def onConnect(self):
        """
        Called when the transport socket is connected to the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session connect")

        # Notify the Wamp router which authentication methods we support
        self.join(self.config.realm, authmethods=WAMP_AUTH_METHODS, authid=WAMP_AUTH_ID)


    async def onChallenge(self, challenge: Challenge):
        """
        Handle the received challenge received from the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session challenged")

        match challenge.method:
            case 'ticket': return self._api._session_info.wstoken
            case _: raise DabPumpsAuthError(f"Unexpected method '{challenge.method} in Challenge received from Wamp server")


    async def onWelcome(self, details: SessionDetails):
        """
        Called when the authentication is accepted by the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session authenticated")


    async def onJoin(self, details: SessionDetails):
        """
        Called when the session is ready for subscribe or procedure call requests to the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session joined")
        self._api._wamp_session_started.set()

        # Resubmit any subscribe requests from previous sessions
        await self._api._wamp_subscribe_resubmit()


    async def onEvent(self, data, details:EventDetails=None):
        """
        Handle data received from the remote Wamp router (i.e. from subscriptions)
        """
        if details is not None:
            await self._api._wamp_event_handler(details.topic, data)
                         

    async def onLeave(self, details):
        """
        Handle a gracious leave from the session by the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session leave")
        self._api._wamp_session_started.clear()

        # Flag all previous subscribe requests as cancelled so they can be resubmitted when we rejoin
        await self._api._wamp_subscribe_cancelled()

                         
    async def onDisconnect(self):
        """
        Handle a disconnect of the transport websocket by the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session disconnect")
        self._api._wamp_runner_started.clear()

        # Flag all previous subscribe requests as cancelled so they can be resubmitted when we reconnect
        await self._api._wamp_subscribe_cancelled()
    