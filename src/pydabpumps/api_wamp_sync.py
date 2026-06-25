"""
api.py: DabPumps API for DAB Pumps integration.

The Api can either be used to retrieve data from the DAB Pumps servers via polling,
but also provides functionality to subscribe to push data.
"""

import logging

from .api_base_sync import(
    DabPumpsBase,
)

_LOGGER = logging.getLogger(__name__)


class DabPumps(DabPumpsBase):
    
    def on_device_state(self, serial: str, callback) -> bool:
        """
        Subscribe to status changes for a device.

        Callback must function in form of fn(serial: str, state: DabPumpsDeviceState)

        The passed state only contains the updated statuses. 
        To get all statuses ignore the state param and instead call:
            state = api.device_state_map.get(serial)
        """
        raise NotImplementedError("Subscribing to push data is not supported in the synchronous version of the DabPumps library. Please switch to the asynchonous library.")
