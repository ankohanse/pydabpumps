import asyncio
import json
import logging
import sys

from dataclasses import asdict
from datetime import datetime

from pydabpumps import (
    AsyncDabPumps,
    DabPumpsStatusCode,
    DabPumpsLogin,
    DabPumpsDevice,
    DabPumpsDeviceState,
)


# Setup logging to StdOut
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format='%(asctime)s: %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


TEST_USERNAME = "fill in your DConnect username here"
TEST_PASSWORD = "fill in your DConnect password here"
#
# Comment out the line below if username and password are set above
from tests import TEST_USERNAME, TEST_PASSWORD


async def main():
    api = None
    try:
        # Process these calls in the right order
        api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
        await api.login()

        # Retrieve translations (optional)
        # Possible languages:
        #    "cs": "Czech",
        #    "nl": "Dutch",
        #    "en": "English",
        #    "fr": "French",
        #    "de": "German",
        #    "it": "Italian",
        #    "pl": "Polish",
        #    "ro": "Romanian",
        #    "ru": "Russian",
        #    "sk": "Slovenian",
        #    "es": "Spanish",
        #    "sf": "Swedish",
        await api.fetch_strings('en')

        # Retrieve installations accessible by this user.
        # Usually only one and you can skip this call if you already know the install_id
        await api.fetch_install_list()

        logger.info(f"installs: {len(api.install_map)}")

        for install_id, install in api.install_map.items():
            logger.info("")
            logger.info(f"installation: {install.name} ({install.id})")

            # Retrieve installation details
            # This includes the list of devices, configuration meta data for each device
            # and initial statuses for each device
            await api.fetch_install_details(install_id)

        logger.info(f"devices: {len(api.device_map)}")

        for device in api.device_map.values():
            # Log the retrieved info
            logger.info("")
            logger.info(f"device: {device.name} ({device.serial})")                
            for k,v in asdict(device).items():
                logger.info(f"    {k}: {v}")

            config = api.device_config_map.get(device.config_id)
            logger.info("")
            logger.info(f"config: {config.description} ({config.id})")
            logger.info(f"    meta_params: {len(config.meta_params)}")             
            #for k,v in config.meta_params.items():
            #    logger.info(f"        {k}: {v}")


        async def show_device_state(serial: str, device_state: DabPumpsDeviceState = None):
            # Helper function to show updated or all device statuses
            device = api.device_map.get(serial)
            device_state = device_state or api.device_state_map.get(serial)

            logger.info("")
            logger.info(f"State for {device.name}: {len(device_state.status)} statuses")

            for key,status in device_state.status.items():
                if status.code in [DabPumpsStatusCode.HIDDEN]:
                    continue
                
                params = api.get_status_metadata(serial, key)
                if params is None:
                    continue

                value_with_unit = f"{status.value} {params.unit}" if params.unit is not None else status.value
                
                if (status.value != status.code):
                    # Display real-life value and original encoded value
                    logger.info(f"    {params.name}: {value_with_unit} ('{status.code}')")
                else:
                    # Display real-life value, original encoded value is the same
                    logger.info(f"    {params.name}: {value_with_unit}")                

        # Show initial device states and subscribe to state updates
        for serial in api.device_map.keys():
            await show_device_state(device.serial)
            await api.on_device_state(serial, show_device_state)

        # Keep the application alive
        for t in range(60):
            # Regularly repeat the login call to make sure the access-token is renewed when needed.
            # This will also reconnect any push session is it has become disconnected.
            await api.login()

            # In addition to waiting for push statuses to arrive, you can still
            # poll for fresh statuses for all devices in this install
            # await api.fetch_install_statuses(install_id)

            # for serial in api.device_map.keys():
            #     await show_device_state(device.serial)

            # Wait one minute and retrieve install statuses again
            logger.info("")
            logger.info(f"wait")
            await asyncio.sleep(60)

    except Exception as e:
        logger.info(f"Unexpected exception: {e}")

    finally:
        if api:
            await api.close()


asyncio.run(main())  # main loop