import asyncio
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import pytest
import pytest_asyncio

from pydabpumps import (
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsDeviceConfig,
    DabPumpsDeviceState,
    DabPumpsParams,
    DabPumpsStatus,
    DabPumpsParamType,
    DabPumpsUserRole,
)

_LOGGER = logging.getLogger(__name__)


async def test_dict():

    install_obj1 = DabPumpsInstall(id="tst_id", name="tst_name")
    install_obj2 = DabPumpsInstall(id="tst_id", name="tst_name", description="tst_descr", company="tst_company", address="tst_address", role=DabPumpsUserRole.INSTALLER, subscr_ts=datetime.now(tz=timezone.utc), devices=2)
    device_obj = DabPumpsDevice(id="tst_device", serial="tst_serial", name="tst_name", vendor="tst_vendor", product="tst_product", hw_version="tst_version", sw_version="", mac_address="tst_mac", config_id="tst_config_id", install_id="tst_install_id")
    param_obj = DabPumpsParams(name="tst_name", type=DabPumpsParamType.MEASURE, unit="tst", weight=10, values={"1":"one","2":"two"}, min=None, max=None, family="tst_family", group="tst_group", view="ci", change="")
    config_obj1 = DabPumpsDeviceConfig(id="tst_id1", label="tst_label", description="tst_descr", meta_params={})
    config_obj2 = DabPumpsDeviceConfig(id="tst_id2", label="tst_label", description="tst_descr", meta_params={"param_key": param_obj})
    status_obj1 = DabPumpsStatus(code="1", value="one")
    status_obj2 = DabPumpsStatus(code="2", value="two")
    state_obj = DabPumpsDeviceState(status={"tst_key1": status_obj1, "tst_key2": status_obj2}, status_ts=datetime.now(timezone.utc) )

    # Convert obj into dict
    install_dict1 = asdict(install_obj1)
    install_dict2 = asdict(install_obj2)
    device_dict = asdict(device_obj)
    param_dict = asdict(param_obj)
    config_dict1 = asdict(config_obj1)
    config_dict2 = asdict(config_obj2)
    status_dict1 = asdict(status_obj1)
    status_dict2 = asdict(status_obj2)
    state_dict = asdict(state_obj)

    assert install_dict1
    assert install_dict2
    assert device_dict 
    assert param_dict 
    assert config_dict1
    assert config_dict2
    assert status_dict1
    assert status_dict2
    assert state_dict

    # Serialize dict into string
    install_str1 = json.dumps(install_dict1, default=str)
    install_str2 = json.dumps(install_dict2, default=str)
    device_str = json.dumps(device_dict, default=str)
    param_str = json.dumps(param_dict, default=str)
    config_str1 = json.dumps(config_dict1, default=str)
    config_str2 = json.dumps(config_dict2, default=str)
    status_str1 = json.dumps(status_dict1, default=str)
    status_str2 = json.dumps(status_dict2, default=str)
    state_str = json.dumps(state_dict, default=str)

    assert install_str1
    assert install_str2
    assert device_str
    assert param_str
    assert config_str1
    assert config_str2
    assert status_str1
    assert status_str2
    assert state_str

    # Deserialize string back into dict
    install_dict1 = json.loads(install_str1)
    install_dict2 = json.loads(install_str2)
    device_dict = json.loads(device_str)
    param_dict = json.loads(param_str)
    config_dict1 = json.loads(config_str1)
    config_dict2 = json.loads(config_str2)
    status_dict1 = json.loads(status_str1)
    status_dict2 = json.loads(status_str2)
    stat_dict = json.loads(state_str)

    assert isinstance(install_dict1, dict)
    assert isinstance(install_dict2, dict)
    assert isinstance(device_dict, dict)
    assert isinstance(param_dict, dict)
    assert isinstance(config_dict1, dict)
    assert isinstance(config_dict2, dict)
    assert isinstance(status_dict1, dict)
    assert isinstance(status_dict2, dict)
    assert isinstance(state_dict, dict)

    # convert back into an object
    install_object1 = DabPumpsInstall(**install_dict1)
    install_object2 = DabPumpsInstall(**install_dict2)
    assert install_object1 == install_obj1
    assert install_object2 == install_obj2

    device_object = DabPumpsDevice(**device_dict)
    assert device_object == device_obj

    param_object = DabPumpsParams(**param_dict)
    assert param_object == param_obj

    config_object1 = DabPumpsDeviceConfig(**config_dict1)
    config_object2 = DabPumpsDeviceConfig(**config_dict2)
    assert config_object1 == config_obj1
    assert config_object2 == config_obj2

    status_object1 = DabPumpsStatus(**status_dict1)
    status_object2 = DabPumpsStatus(**status_dict2)
    assert status_object1 == status_obj1
    assert status_object2 == status_obj2

    state_object = DabPumpsDeviceState(**state_dict)
    assert state_object == state_obj
