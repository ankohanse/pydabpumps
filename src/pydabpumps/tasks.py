import asyncio
import threading


class AsyncTaskHelper:
    """
    Helper to unify async task create, sleep and stop
    """
    def __init__(self):
         self._task = None
         self._stop_event = asyncio.Event()

    async def start(self, function) -> 'AsyncTaskHelper':
        coro = function()
        self._task = asyncio.create_task(coro=coro, name=function.__name__)
    
    async def stop(self):
        try:
            # Request the stop
            self._stop_event.set()
        
            # await the task to allow it to finish and cleanup
            await self._task

        except asyncio.CancelledError:
            pass

    def is_stop_requested(self):
        return self._stop_event.is_set()
    
    async def wait_for_stop(self, timeout: float):
        """Returns True if stop_event was set, False on timeout"""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
            return True

        except asyncio.TimeoutError:
            return False

         
class TaskHelper:
    """
    Helper to unify sync task create, sleep and stop
    """
    def __init__(self):
         self._task = None
         self._stop_event = threading.Event()

    def start(self, function) -> 'TaskHelper':
        self._task = threading.Thread(target=function, name=function.__name__)
        self._task.start()

    def stop(self):
        # Request the stop
        self._stop_event.set()

        # Wait for the thread to finish
        self._task.join()

    def is_stop_requested(self):
        return self._stop_event.is_set()
    
    def wait_for_stop(self, timeout: float) -> bool:
        """Returns True if stop_event was set, False on timeout"""
        return self._stop_event.wait(timeout=timeout)
         
    