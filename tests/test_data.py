import json
import logging
import pytest
import pytest_asyncio

from dataclasses import asdict
from datetime import datetime, timezone

from pydabpumps import (
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsDeviceConfig,
    DabPumpsDeviceState,
    DabPumpsParams,
    DabPumpsParamType,
    DabPumpsStatus,
    DabPumpsUserRole,
    DabPumpsLogin, 
    DabPumpsLoginInfo,
    DabPumpsAccessTokenInfo,
    DabPumpsRefreshTokenInfo,
    DabPumpsHistoryDetail, 
    DabPumpsHistoryItem,
    to_dict,
    utcnow,
    utcmin,
)

_LOGGER = logging.getLogger(__name__)


async def test_dataclasses():

    install_obj1 = DabPumpsInstall(id="tst_id", name="tst_name")
    install_obj2 = DabPumpsInstall(id="tst_id", name="tst_name", description="tst_descr", company="tst_company", address="tst_address", role=DabPumpsUserRole.INSTALLER, subscr_ts=datetime.now(tz=timezone.utc), devices=2)
    device_obj = DabPumpsDevice(id="tst_device", serial="tst_serial", name="tst_name", vendor="tst_vendor", product="tst_product", hw_version="tst_version", sw_version="", mac_address="tst_mac", config_id="tst_config_id", install_id="tst_install_id")
    param_obj = DabPumpsParams(name="tst_name", type=DabPumpsParamType.MEASURE, unit="tst", weight=10, values={"1":"one","2":"two"}, min=None, max=None, family="tst_family", group="tst_group", view="ci", change="")
    config_obj1 = DabPumpsDeviceConfig(id="tst_id1", label="tst_label", description="tst_descr", meta_params={})
    config_obj2 = DabPumpsDeviceConfig(id="tst_id2", label="tst_label", description="tst_descr", meta_params={"param_key": param_obj})
    status_obj1 = DabPumpsStatus(code="1", value="one")
    status_obj2 = DabPumpsStatus(code="2", value="two")
    state_obj = DabPumpsDeviceState(status={"tst_key1": status_obj1, "tst_key2": status_obj2}, status_ts=utcnow(), lastrecv_ts=utcnow(), online=True, state="OK")

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


async def test_info():

    login_obj = DabPumpsLoginInfo(login_method=DabPumpsLogin.H2D_APP, retry_schedule=utcmin(), retry_count=0)
    access_obj = DabPumpsAccessTokenInfo(token="access_token", expires_in=30, expiry=utcnow())
    refresh_obj = DabPumpsRefreshTokenInfo(token="refresh_token", expires_in=3600, expiry=utcnow(), client_id="client_id", client_secret="client_secret", retry_schedule=utcmin(), retry_count=0)

    # Convert obj into dict.
    login_dict = asdict(login_obj)
    access_dict = asdict(access_obj)
    refresh_dict = asdict(refresh_obj)

    assert login_dict
    assert access_dict
    assert refresh_dict 

    # Serialize dict into string
    login_str = json.dumps(login_dict, default=str)
    access_str = json.dumps(access_dict, default=str)
    refresh_str = json.dumps(refresh_dict, default=str)

    assert login_str
    assert access_str
    assert refresh_str

    # Deserialize string back into dict
    login_dict = json.loads(login_str)
    access_dict = json.loads(access_str)
    refresh_dict = json.loads(refresh_str)

    assert isinstance(login_dict, dict)
    assert isinstance(access_dict, dict)
    assert isinstance(refresh_dict, dict)

    # convert back into an object
    login_object = DabPumpsLoginInfo(**login_dict)
    access_object = DabPumpsAccessTokenInfo(**access_dict)
    refresh_object = DabPumpsRefreshTokenInfo(**refresh_dict)

    assert login_object == login_obj
    assert access_object == access_obj
    assert refresh_object == refresh_obj


async def test_history():

    item1 = DabPumpsHistoryItem(ts=utcnow(), op="GET", rsp="OK 1")
    item2 = DabPumpsHistoryItem(ts=utcnow(), op="GET", rsp="OK 2")
    item3 = DabPumpsHistoryItem(ts=utcnow(), op="GET", rsp="OK 3")
    detail1 = DabPumpsHistoryDetail(ts=utcnow(), req={'a':'1', 'b':'2', 'c':'3'}, rsp={'x':'X', 'y':'Y', 'z':'Z'}, token={'t':'ABC'})
    detail2 = DabPumpsHistoryDetail(ts=utcnow(), req={'a':'1', 'b':'2', 'c':None}, rsp={'x':'X', 'y':'Y', 'z':None}, token=None)

    data = {
        'items': [item1, item2, item3],
        'details': [detail1, detail2]
    }

    # Using to_dict for these dataclasses as it provides some special functionality:
    # - Handle datetime
    # - Handle Mappings
    # - Hide None values
    result = to_dict(data)

    assert result is not None
    assert isinstance(result, dict)
    assert len(result) == 2

    assert 'items' in result
    assert isinstance(result['items'], list)
    assert len(result['items']) == 3

    i1 = result['items'][0]
    assert isinstance(i1, dict)
    assert 'ts' in i1
    assert isinstance(i1['ts'], str)    # datetime must be converted into isoformat string

    assert 'details' in result
    assert isinstance(result['details'], list)
    assert len(result['details']) == 2

    # Check None value is removed
    d1 = result['details'][0]
    assert isinstance(d1, dict)
    assert 'ts' in d1
    assert isinstance(d1['ts'], str)    # datetime must be converted into isoformat string

    assert 'req' in d1
    assert isinstance(d1['req'], dict)
    assert 'c' in d1['req']             # Expected value must be there

    assert 'rsp' in d1
    assert isinstance(d1['rsp'], dict)
    assert 'z' in d1['rsp']             # Expected value must be there

    assert 'token' in d1
    assert isinstance(d1['token'], dict)
    assert 't' in d1['token']           # Expected value must be there

    d2 = result['details'][1]
    assert isinstance(d2, dict)
    assert 'ts' in d2
    assert isinstance(d2['ts'], str)    # datetime must be converted into isoformat string

    assert 'req' in d2
    assert isinstance(d2['req'], dict)
    assert 'c' not in d2['req']         # Inner None value must be removed

    assert 'rsp' in d2
    assert isinstance(d2['rsp'], dict)
    assert 'z' not in d2['rsp']         # Inner None value must be removed

    assert 'token' not in d2            # None value must be removed
