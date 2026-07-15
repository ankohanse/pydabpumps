"""
api.py: DabPumps API for DAB Pumps integration.

The Api can either be used to retrieve data from the DAB Pumps servers via polling,
but also provides functionality to subscribe to push data.
"""

import asyncio
import httpx
import logging
import ssl

from autobahn.asyncio.component import Component as WampComponent
from autobahn.asyncio.wamp import ApplicationSession
from autobahn.wamp import CloseDetails, ComponentConfig, EventDetails, SessionDetails, SubscribeOptions
from autobahn.wamp.types import Challenge, Subscription

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, parse_qs


from .api_base_async import(
    AsyncDabPumpsBase,
)
from .const import (
    WAMP_HOST,
    WAMP_PORT,
    WAMP_URL,
    WAMP_REALM,
    WAMP_AUTH_METHODS,
    WAMP_AUTH_ID,
    WAMP_START_TIMEOUT,
    WAMP_REPEAT_TIMEOUT_MIN,
    WAMP_REPEAT_TIMEOUT_MAX,
    utcnow,
    utcmin,
)
from .data import (
    DabPumpsAuthError,
    DabPumpsDeviceState,
    DabPumpsError,
    DabPumpsLogin,
    DabPumpsLoginInfo,
    DabPumpsAccessTokenInfo,
    DabPumpsRefreshTokenInfo,
)
from .tasks import (
    AsyncTaskHelper,
)


_LOGGER = logging.getLogger(__name__)


class WampMethod(StrEnum):
    SUBSCRIBE = 'WampSubscribe'
    SUBSCRIBED = 'WampSubscribed'
    EVENT = 'WampEvent'


class WampSubscriptionType(StrEnum):
    DEVICE_STATE = 'DeviceState'

class WampCloseReason(StrEnum):
    DABPUMPS_NO_SUCH_USER = 'com.dabpumps.no_such_user'
    CLOSE_NORMAL = CloseDetails.REASON_DEFAULT # 'wamp.close.normal',
    CLOSE_TRANSPORT_LOST = CloseDetails.REASON_TRANSPORT_LOST  # 'wamp.close.transport_lost'


@dataclass
class WampSubscriptionDetails:
    context: str = None
    request: dict = None
    response: dict = None
    callback: Any = None


class AsyncDabPumps(AsyncDabPumpsBase):
    
    def __init__(self, username, password, client:httpx.AsyncClient=None, ssl_context:ssl.SSLContext=None, login_info:DabPumpsLoginInfo=None, access_token_info:DabPumpsAccessTokenInfo=None, refresh_token_info:DabPumpsRefreshTokenInfo=None):
        super().__init__(
            username = username, 
            password = password, 
            client = client,
            ssl_context = ssl_context,
            login_info = login_info, 
            access_token_info = access_token_info, 
            refresh_token_info = refresh_token_info
        )
        
        # Wamp component and session
        self._wamp_component = WampComponent(
            transports = [
                {
                    "type": "websocket",
                    "url": WAMP_URL,
                    "endpoint": {
                        "type": "tcp",
                        "host": WAMP_HOST,
                        "port": WAMP_PORT,
                        "tls": self._ssl_context,                                                                                                                   
                    },
                },
            ],
            realm = WAMP_REALM,
            session_factory = self._wamp_session_factory,
        )
        self._wamp_component_task: asyncio.Future = None
        self._wamp_component_started = asyncio.Event()
        self._wamp_session: ApplicationSession = None
        self._wamp_session_started = asyncio.Event()
        self._wamp_session_start_ts: datetime = utcmin()
        self._wamp_subscription_map: dict[str, WampSubscriptionDetails] = {}    # topic -> { context, request, response, callback }

        # Automatic re-connect to wamp_session        
        self._wamp_reconnect_task = AsyncTaskHelper(
            name="Reconnect handler", 
            action=self._wamp_reconnect_handler, 
            repeat_timeout_min=WAMP_REPEAT_TIMEOUT_MIN, 
            repeat_timeout_max=WAMP_REPEAT_TIMEOUT_MAX
        )


    async def login(self, test_method:DabPumpsLogin=None):
        """
        Login to DAB Pumps by trying each of the possible login methods.
        Guards for calls from multiple threads.

        Also makes sure that the Wamp/Push connection is restored if is was previously used
        """

        # Login via Http
        await super().login(test_method)
            
        if not self._wamp_reconnect_task.running:
            await self._wamp_reconnect_task.start()


    async def close(self):
        """Safely logout and close all client handles"""

        # Stop Wamp session and user session
        await self._wamp_reconnect_task.stop()
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

        # Subscribe to status changes works with all login methods, except DCONNECT_WEB
        if self._login_info.login_method in [DabPumpsLogin.DCONNECT_WEB]:
            raise DabPumpsError(f"Subscribe to push data is not supported for login method {self._login_info.login_method}")

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

        # Trigger the reconnect handler to immediately connect if needed
        await self._wamp_reconnect_task.schedule(utcnow())


    async def _wamp_reconnect_handler(self):
        """
        Check if the Wamp session needs reconnecting
        """        
        if self._wamp_subscription_map:
            await self._start_user_session()
            await self._start_wamp_session()


    async def _start_wamp_session(self) -> bool:
        """
        Start Wamp/push handler
        """
        if not self._session_info.wstoken:
            return False    # requirements not met

        # Check if component and session are already started
        if self._wamp_component_started.is_set():
            if self._wamp_session_started.is_set():
                return True     # Already started
            
            elif (utcnow() - self._wamp_session_start_ts).seconds < WAMP_START_TIMEOUT:
                return True     # Still starting
            
        # Not started yet, or session start failed
        try:
            self._wamp_component_task = self._wamp_component.start(loop=asyncio.get_event_loop())
            self._wamp_component_task.add_done_callback(self._wamp_done_handler)
            self._wamp_component_started.set()

            # Schedule repeated checks of session start success
            await self._wamp_reconnect_task.schedule(None)
            return True

        except Exception as e:
            _LOGGER.debug(f"Unable to start Wamp session, got exception '{str(e)}'")
            return False


    async def _stop_wamp_session(self):
        """
        Stop Wamp/push handler
        """
        if self._wamp_component_started.is_set():
            self._wamp_component.stop()
            self._wamp_component_started.clear()

        # Component will take care of stopping the session


    def _wamp_session_factory(self, config):
        """
        Factory to create an Wamp session object
        """
        self._wamp_session = AsyncDabPumpsWampSession(config, api_instance=self)
        self._wamp_session_start_ts = utcnow()
        self._wamp_session_started.clear()

        _LOGGER.debug(f"Wamp session created")
        return self._wamp_session
    

    async def _wamp_subscribe_cancelled(self):
        """
        Flag any previous wamp requests as cancelled so that they will be resubmitted in a next session
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

        # Perform the request
        serial = request['device_serial']
        topic = request['topic']
        timestamp = utcnow()
        response = {}
        try:
            # Remember this subscription request in case we need to reconnect later
            self._wamp_subscription_map[topic] = WampSubscriptionDetails(context=context, request=request, response=None, callback=callback)

            # If session is not (yet) joined then we're done. Wamp request will be triggered once (re-)joined
            if not self._wamp_session_started.is_set():
                return True
            
            # Subscribe now
            _LOGGER.info(f"Subscribe to changes for device '{serial}' via topic '{topic}'")

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

                _LOGGER.debug(f"State updated for '{serial}' with {len(values)} values")

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


    async def _wamp_join_handler(self):
        """
        Handle a wamp join
        """
        self._wamp_session_started.set()

        # Resubmit any subscribe requests from previous sessions
        await self._wamp_subscribe_resubmit()

        
    async def _wamp_leave_handler(self, reason:str=None):
        """
        handle wamp leave/disconnect received from the DAB Pumps servers
        """          
        self._wamp_session_start_ts = utcmin()
        self._wamp_session_started.clear()

        # If needed, trigger restart of user session
        if reason in [WampCloseReason.DABPUMPS_NO_SUCH_USER]:
            self._session_info.wstoken = None

        # Diagnostics
        self._session_info.leave_reasons.add(reason)

        # Flag all previous subscribe requests as cancelled so they can be resubmitted once we rejoin
        await self._wamp_subscribe_cancelled()

        # Trigger an immediate reconnect attempt
        await self._wamp_reconnect_task.schedule(utcnow())


    def _wamp_done_handler(self, task:asyncio.Future=None):
        """
        handle wamp component done.
        Note: used as param in asyncio.add_done_callback, which expects a sync function def!
        """ 
        _LOGGER.debug(f"Wamp component done")
        try:
            result = task.result()
        except:
            pass
        finally:
            self._wamp_component_started.clear()
        
        # Make sure we cleanup the session in case it was not already done
        asyncio.create_task(self._wamp_leave_handler())
        

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
            case 'ticket': return self._api._session_info.wstoken or ""
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
        await self._api._wamp_join_handler()


    async def onEvent(self, data, details:EventDetails=None):
        """
        Handle data received from the remote Wamp router (i.e. from subscriptions)
        """
        if details is not None:
            await self._api._wamp_event_handler(details.topic, data)
                         

    async def onLeave(self, details:CloseDetails):
        """
        Handle a gracious leave from the session by the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session leave ({details.reason})")
        await self._api._wamp_leave_handler(details.reason)

                         
    async def onDisconnect(self):
        """
        Handle a disconnect of the transport websocket by the remote Wamp router
        """
        _LOGGER.debug(f"Wamp session disconnect")
        await self._api._wamp_leave_handler()

    