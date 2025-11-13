import asyncio
import copy
from dataclasses import asdict
from datetime import datetime
import json
import logging
import pytest
import pytest_asyncio

from pydabpumps import (
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsConfig,
    DabPumpsParams,
    DabPumpsStatus,
    DabPumpsParamType,
    DabPumpsUserRole,
)

_LOGGER = logging.getLogger(__name__)


async def test_dict():

    install_obj = DabPumpsInstall(id="tst_id", name="tst_name", description="tst_descr", company="tst_company", address="tst_address", role=DabPumpsUserRole.INSTALLER, devices=2)
    device_obj = DabPumpsDevice(id="tst_id", serial="tst_serial", name="tst_name", vendor="tst_vendor", product="tst_product", hw_version="tst_version", sw_version="", mac_address="tst_mac", config_id="tst_config_id", install_id="tst_install_id")
    param_obj = DabPumpsParams(key="tst_key", name="tst_name", type=DabPumpsParamType.MEASURE, unit="tst", weight=10, values={"1":"one","2":"two"}, min=None, max=None, family="tst_family", group="tst_group", view="ci", change="", log="", report="")
    config_obj1 = DabPumpsConfig(id="tst_id", label="tst_label", description="tst_descr", meta_params={})
    config_obj2 = DabPumpsConfig(id="tst_id", label="tst_label", description="tst_descr", meta_params={"param_key": param_obj})
    status_obj1 = DabPumpsStatus(serial="tst_serial", key="tst_key", name="tst_name", code="1", value="one", unit="tst_unit", status_ts=None, update_ts=None )
    status_obj2 = DabPumpsStatus(serial="tst_serial", key="tst_key", name="tst_name", code="1", value="one", unit="tst_unit", status_ts=datetime.now(), update_ts=datetime.now() )

    # Convert obj into dict
    install_dict = asdict(install_obj)
    device_dict = asdict(device_obj)
    param_dict = asdict(param_obj)
    config_dict1 = asdict(config_obj1)
    config_dict2 = asdict(config_obj2)
    status_dict1 = asdict(status_obj1)
    status_dict2 = asdict(status_obj2)

    assert install_dict
    assert device_dict 
    assert param_dict 
    assert config_dict1
    assert config_dict2
    assert status_dict1
    assert status_dict2

    # Serialize dict into string
    install_str = json.dumps(install_dict, default=str)
    device_str = json.dumps(device_dict, default=str)
    param_str = json.dumps(param_dict, default=str)
    config_str1 = json.dumps(config_dict1, default=str)
    config_str2 = json.dumps(config_dict2, default=str)
    status_str1 = json.dumps(status_dict1, default=str)
    status_str2 = json.dumps(status_dict2, default=str)

    assert install_str
    assert device_str
    assert param_str
    assert config_str1
    assert config_str2
    assert status_str1
    assert status_str2

    # Deserialize string back into dict
    install_dict = json.loads(install_str)
    device_dict = json.loads(device_str)
    param_dict = json.loads(param_str)
    config_dict1 = json.loads(config_str1)
    config_dict2 = json.loads(config_str2)
    status_dict1 = json.loads(status_str1)
    status_dict2 = json.loads(status_str2)

    assert isinstance(install_dict, dict)
    assert isinstance(device_dict, dict)
    assert isinstance(param_dict, dict)
    assert isinstance(config_dict1, dict)
    assert isinstance(config_dict2, dict)
    assert isinstance(status_dict1, dict)
    assert isinstance(status_dict2, dict)

    # convert back into an object
    install_object = DabPumpsInstall(**install_dict)
    assert install_object == install_obj

    device_object = DabPumpsDevice(**device_dict)
    assert device_object == device_obj

    param_object = DabPumpsParams(**param_dict)
    assert param_object == param_obj

    config_object1 = DabPumpsConfig(**config_dict1)
    config_object2 = DabPumpsConfig(**config_dict2)
    assert config_object1 == config_obj1
    assert config_object2 == config_obj2

    status_object1 = DabPumpsStatus(**status_dict1)
    status_object2 = DabPumpsStatus(**status_dict2)
    assert status_object1 == status_obj1
    assert status_object2 == status_obj2
