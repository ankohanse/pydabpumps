import logging
import sys
import time

from dataclasses import asdict
from datetime import datetime

from pydabpumps import DabPumps

# Setup logging to StdOut
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


TEST_USERNAME = "fill in your DConnect username here"
TEST_PASSWORD = "fill in your DConnect password here"
#
# Comment out the line below if username and password are set above
from tests import TEST_USERNAME, TEST_PASSWORD


def main():
    api = None
    try:
        # Process these calls in the right order
        api = DabPumps(TEST_USERNAME, TEST_PASSWORD)
        api.login()

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
        api.fetch_strings('en')

        # Retrieve installations accessible by this user.
        # Usually only one and you can skip this call if you already know the install_id
        api.fetch_install_list()

        logger.info(f"installs: {len(api.install_map)}")

        for install_id, install in api.install_map.items():
            logger.info("")
            logger.info(f"installation: {install.name} ({install.id})")

            # Retrieve installation details
            # This includes the list of devices, configuration meta data for each device
            # and initial statuses for each device
            api.fetch_install_details(install_id)

        logger.info(f"devices: {len(api.device_map)}")

        for device in api.device_map.values():
            # Log the retrieved info
            logger.info("")
            logger.info(f"device: {device.name} ({device.serial})")                
            for k,v in asdict(device).items():
                logger.info(f"    {k}: {v}")

            config = api.config_map[device.config_id]                     
            logger.info("")
            logger.info(f"config: {config.description} ({config.id})")
            logger.info(f"    meta_params: {len(config.meta_params)}")             
            #for k,v in config.meta_params.items():
            #    logger.info(f"        {k}: {v}")

        # Once the calls above have been perfomed, the calls below can be repeated periodically.
        for t in range(60):
            # Regularly repeat the login call to make sure the access-token is renewed when needed.
            api.login()

            # Retrieve fresh statuses for all devices in this install
            api.fetch_install_statuses(install_id)

            for device in api.device_map.values():
                device_statuses = { k:v for k,v in api.status_map.items() if v.serial==device.serial }
                logger.info("")
                logger.info(f"statuses for {device.name}: {len(device_statuses)}")

                for k,v in device_statuses.items():
                    value_with_unit = f"{v.value} {v.unit}" if v.unit is not None else v.value

                    if (v.value != v.code):
                        # Display real-life value and original encoded value
                        logger.info(f"    {v.name}: {value_with_unit} ('{v.code}')")
                    else:
                        # Display real-life value, original encoded value is the same
                        logger.info(f"    {v.name}: {value_with_unit}")

            # Wait one minute and retrieve install statuses again
            logger.info("")
            logger.info(f"wait ({datetime.now().strftime("%H:%M")})")
            time.sleep(60)

    except Exception as e:
        logger.info(f"Unexpected exception: {e}")

    finally:
        if api:
            api.close()


main()  # main loop