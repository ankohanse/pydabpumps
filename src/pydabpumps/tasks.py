import asyncio
from datetime import datetime
import logging
import threading

from .const import (
    utcnow,
)

_LOGGER = logging.getLogger(__name__)


class AsyncTaskHelper:
    """
    Helper to unify async task create, sleep and stop
    """
    def __init__(self, name: str, action, repeat_timeout_min:float=60, repeat_timeout_max:float=300, repeat_timeout_factor: float=1.5):
        self._name = name
        self._action = action
        self._repeat_timeout_min = repeat_timeout_min
        self._repeat_timeout_max = repeat_timeout_max
        self._repeat_timeout_factor = repeat_timeout_factor

        self._scheduled_timeout = None
        self._repeat_timeout = 0
        
        self._task = None
        self._stop_event = asyncio.Event()
        self._wakeup_event = asyncio.Event()

    @property
    def running(self):
        return self._task is not None
    
    async def start(self):
        self._task = asyncio.create_task(self._loop(), name=self._name)
        
    async def stop(self):
        try:
            # Request the stop and
            # await the task to allow it to finish and cleanup
            self._stop_event.set()
            self._wakeup_event.set()
            if self._task is not None:
                await self._task
                self._task = None

        except asyncio.CancelledError:
            pass

    async def schedule(self, schedule: datetime):
        self._scheduled_timeout = schedule
        self._repeat_timeout = 0
        self._wakeup_event.set()
        
    async def _loop(self):
        _LOGGER.debug(f"{self._name} started")

        while not self._stop_event.is_set():

            self._wakeup_event.clear()
            if self._scheduled_timeout is not None:
                # Wait until schedule, or wakeup immediately
                timeout = max((self._scheduled_timeout - utcnow()).total_seconds(), 0)
            else:
                # Wait for repeat_timeout
                self._repeat_timeout *= self._repeat_timeout_factor
                self._repeat_timeout = min(max(self._repeat_timeout, self._repeat_timeout_min), self._repeat_timeout_max)
                timeout = self._repeat_timeout

            try:
                await asyncio.wait_for(self._wakeup_event.wait(), timeout)

                # Stop or reschedule detected
                continue

            except asyncio.TimeoutError:
                # Clear schedule, next timeout will be after repeat_timeout seconds.
                # Unless the action sets a new schedule.
                self._scheduled_timeout = None

                # Call the action
                await self._action()

            except Exception as ex:
                _LOGGER.debug(f"{self._name} caught exception: {ex}")

        _LOGGER.debug(f"{self._name} stopped")
        return True

         
class TaskHelper:
    """
    Helper to unify sync task create, sleep and stop
    """
    def __init__(self, name: str, action, repeat_timeout_min:float=60, repeat_timeout_max:float=300, repeat_timeout_factor: float=1.5):
        self._name = name
        self._action = action
        self._repeat_timeout_min = repeat_timeout_min
        self._repeat_timeout_max = repeat_timeout_max
        self._repeat_timeout_factor = repeat_timeout_factor

        self._scheduled_timeout = None
        self._repeat_timeout = 0

        self._task = None
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()

    @property
    def running(self):
        return self._task is not None
    
    def start(self):
        self._task = threading.Thread(target=self._loop, name=self._name)
        self._task.start()

    def stop(self):
        # Request the stop and
        # wait for the thread to finish and cleanup
        self._stop_event.set()
        self._wakeup_event.set()
        if self._task is not None:
            self._task.join()
            self._task = None

    def schedule(self, schedule: datetime):
        self._scheduled_timeout = schedule
        self._repeat_timeout = 0
        self._wakeup_event.set()

    def _loop(self):
        _LOGGER.debug(f"{self._name} started")

        while not self._stop_event.is_set():
            
            self._wakeup_event.clear()
            if self._scheduled_timeout is not None:
                # Wait until schedule, or wakeup immediately
                timeout = max((self._scheduled_timeout - utcnow()).total_seconds(), 0)
            else:
                # Wait for repeat_timeout
                self._repeat_timeout *= self._repeat_timeout_factor
                self._repeat_timeout = min(max(self._repeat_timeout, self._repeat_timeout_min), self._repeat_timeout_max)
                timeout = self._repeat_timeout

            if self._wakeup_event.wait(timeout):
                # Stop or reschedule detected
                continue
            else:
                # Clear schedule, next timeout will be after repeat_timeout seconds.
                # Unless the action sets a new schedule.
                self._scheduled_timeout = None

                # Call the action
                self._action()

        _LOGGER.debug(f"{self._name} stopped")
        return True
         
    