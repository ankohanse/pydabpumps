import asyncio
import copy
import logging
import pytest
import pytest_asyncio

from datetime import datetime, timezone

from pydabpumps import (
    AsyncDabPumps,
    DabPumps,
    DabPumpsAuthError,
    DabPumpsConnectError,
    DabPumpsError, 
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsDeviceConfig,
    DabPumpsDeviceState,
    DabPumpsParams,
    DabPumpsStatus,
    DabPumpsParamType,
    DabPumpsUserRole,
    DabPumpsLoginInfo,
    DabPumpsAccessTokenInfo,
    DabPumpsRefreshTokenInfo,
    DabPumpsHistoryItem, 
    DabPumpsHistoryDetail,
    DabPumpsLogin,
    DabPumpsFetch,
    utcnow,
    utcmin,
)

from . import TEST_USERNAME, TEST_PASSWORD
from . import TEST_FRAMEWORK_ASYNC, TEST_FRAMEWORK_SYNC

_LOGGER = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class TestContext:
    def __init__(self):
        self.api = None
        self.framework = TEST_FRAMEWORK_ASYNC

    async def cleanup(self):
        if self.api:
            await self.api.logout()
            await self.api.close()
            assert self.api.closed == True


@pytest_asyncio.fixture
async def context():
    # Prepare
    ctx = TestContext()

    # pass objects to tests
    yield ctx

    # cleanup
    await ctx.cleanup()


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, method, usr, pwd, exp_except",
    [
        ("ok",   None,                        TEST_USERNAME, TEST_PASSWORD, None),
        ("ok",   DabPumpsLogin.H2D_APP,       TEST_USERNAME, TEST_PASSWORD, None),
        ("ok",   DabPumpsLogin.DABLIVE_APP,   TEST_USERNAME, TEST_PASSWORD, None),
        ("ok",   DabPumpsLogin.DCONNECT_APP,  TEST_USERNAME, TEST_PASSWORD, None),
        ("ok",   DabPumpsLogin.DCONNECT_WEB,  TEST_USERNAME, TEST_PASSWORD, None),
        ("fail", None,                        "dummy_usr",   "wrong_pwd",   DabPumpsAuthError),
        ("fail", DabPumpsLogin.H2D_APP,       "dummy_usr",   "wrong_pwd",   DabPumpsAuthError),
        ("fail", DabPumpsLogin.DABLIVE_APP,   "dummy_usr",   "wrong_pwd",   DabPumpsAuthError),
        ("fail", DabPumpsLogin.DCONNECT_APP,  "dummy_usr",   "wrong_pwd",   DabPumpsAuthError),
        ("fail", DabPumpsLogin.DCONNECT_WEB,  "dummy_usr",   "wrong_pwd",   DabPumpsAuthError),
    ]
)
async def test_login(name, method, usr, pwd, exp_except, request):
    context = request.getfixturevalue("context")
    assert context.api is None

    context.api = AsyncDabPumps(usr, pwd)
    assert context.api.closed == False

    if exp_except is None:
        assert not context.api.login_active
        assert context.api.login_info is not None
        assert context.api.login_info.login_method is None

        await context.api.login(method)

        assert context.api.login_active
        assert context.api.login_info is not None
        assert context.api.login_info.login_method is not None

        if method != DabPumpsLogin.DCONNECT_WEB:
            assert context.api.access_token_info is not None
            assert context.api.access_token_info.token is not None
            assert context.api.access_token_info.expiry > utcmin()
            assert context.api.refresh_token_info is not None
            assert context.api.refresh_token_info.token is not None
            assert context.api.refresh_token_info.expiry > utcmin()

        assert context.api.install_map is not None
        assert context.api.device_map is not None
        assert context.api.device_config_map is not None
        assert context.api.device_state_map is not None
        assert context.api.string_map is not None
        assert len(context.api.install_map) == 0
        assert len(context.api.device_map) == 0
        assert len(context.api.device_config_map) == 0
        assert len(context.api.device_state_map) == 0
        assert len(context.api.string_map) == 0

    else:
        with pytest.raises(exp_except):
            await context.api.login(method)


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, usr, pwd, exp_except",
    [
        ("login multi", TEST_USERNAME, TEST_PASSWORD, None),
    ]
)
async def test_login_seq(name, usr, pwd, exp_except, request):
    context = request.getfixturevalue("context")
    assert context.api is None

    # First call with wrong pwd
    context.api = AsyncDabPumps(usr, "wrong_pwd")
    assert context.api.closed == False
    assert not context.api.login_active
    assert context.api.login_info is not None
    assert context.api.login_info.login_method is None

    with pytest.raises(DabPumpsAuthError):
        await context.api.login()

    # Next call with correct pwd
    context.api = AsyncDabPumps(usr, pwd)
    assert context.api.closed == False
    assert not context.api.login_active
    assert context.api.login_info is not None
    assert context.api.login_info.login_method is None

    if exp_except is None:
        await context.api.login()

        assert context.api.login_active
        assert context.api.login_info is not None
        assert context.api.login_info.login_method is not None
        assert context.api.install_map is not None
        assert context.api.device_map is not None
        assert context.api.device_config_map is not None
        assert context.api.device_state_map is not None
        assert context.api.string_map is not None
        assert len(context.api.install_map) == 0
        assert len(context.api.device_map) == 0
        assert len(context.api.device_config_map) == 0
        assert len(context.api.device_state_map) == 0
        assert len(context.api.string_map) == 0

    else:
        with pytest.raises(exp_except):
            await context.api.login()


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, method, loop, exp_except",
    [
        ("ok",  None,                        0, None),
        ("ok",  DabPumpsLogin.H2D_APP,       0, None),
        ("ok",  DabPumpsLogin.DABLIVE_APP,   0, None),
        ("ok",  DabPumpsLogin.DCONNECT_APP,  0, None),
        ("ok",  DabPumpsLogin.DCONNECT_WEB,  0, None),
        #
        #("24h", None,                        24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.H2D_APP,       24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.DABLIVE_APP,   24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.DCONNECT_APP,  24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.DCONNECT_WEB,  24*60, None),    # Run 1 full day
    ]
)
async def test_get_data(name, method, loop, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Try set diagnostics callback function
    context.api.set_diagnostics(lambda context,item,detail,data: None)

    # Login
    await context.api.login(method)

    login_method_org = context.api.login_info.login_method

    # Get install list
    await context.api.fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    for install_id,install in context.api.install_map.items():
        assert type(install_id) is str
        assert type(install) is DabPumpsInstall
        assert install.id is not None    
        assert install.name is not None  
        assert install.role is not None
        assert install.subscr_ts is None or type(install.subscr_ts) is datetime

    # Get install details, config metadata and initial statuses (just for the first install)
    await context.api.fetch_install_details(install_id)

    assert context.api.device_map is not None
    assert type(context.api.device_map) is dict
    assert len(context.api.device_map) > 0

    for device_serial,device in context.api.device_map.items():
        assert type(device_serial) is str
        assert type(device) is DabPumpsDevice
        assert device.serial is not None    
        assert device.name is not None  
        assert device.config_id is not None  
        assert device.install_id is not None  

    assert context.api.device_config_map is not None
    assert type(context.api.device_config_map) is dict
    assert len(context.api.device_config_map) > 0

    for config_id,config in context.api.device_config_map.items():
        assert type(config_id) is str
        assert type(config) is DabPumpsDeviceConfig
        assert config.id is not None
        assert config.label is not None

        assert config.meta_params is not None
        assert type(config.meta_params) is dict
        assert len(config.meta_params) > 0

        for param_key,param in config.meta_params.items():
            assert type(param_key) is str
            assert type(param) is DabPumpsParams

    assert context.api.device_state_map is not None
    assert type(context.api.device_state_map) is dict
    assert len(context.api.device_state_map) > 0

    for device_serial,device_state in context.api.device_state_map.items():
        assert type(device_serial) is str
        assert type(device_state) is DabPumpsDeviceState
        assert device_state.status_ts is not None
        assert device_state.status is not None
        assert type(device_state.status) is dict
        assert len(device_state.status) > 0

        for status_key,status in device_state.status.items():
            assert type(status_key) is str
            assert type(status) is DabPumpsStatus
            assert status.code is not None
            assert status.value is not None

    counter_success: int = 0
    counter_fail: int = 0
    reason_fail: dict[str,int] = {}
    for idx in range(1,loop+1):
        # Get fresh device statuses
        try:
            # Check access-token and refresh or re-login if needed
            await context.api.login()
            assert login_method_org == context.api.login_info.login_method

            await context.api.fetch_install_statuses(install_id)

            assert context.api.device_state_map is not None
            assert type(context.api.device_state_map) is dict
            assert len(context.api.device_state_map) > 0

            for device_serial,device_state in context.api.device_state_map.items():
                assert type(device_serial) is str
                assert type(device_state) is DabPumpsDeviceState
                assert device_state.status_ts is not None
                assert device_state.status is not None
                assert type(device_state.status) is dict
                assert len(device_state.status) > 0

                for status_key,status in device_state.status.items():
                    assert type(status_key) is str
                    assert type(status) is DabPumpsStatus
                    assert status.code is not None
                    assert status.value is not None

            counter_success += 1
        
        except Exception as ex:
            counter_fail += 1
            reason = str(ex)
            reason_fail[reason] = reason_fail[reason]+1 if reason in reason_fail else 1
            _LOGGER.warning(f"Fail: {ex}")

        if loop:
            # Simulate failure to recover from
            #if idx % 6 == 0:
            #    await context.api._logout("simulate failure")
            #elif idx % 3 == 0:
            #    await context.api._logout("login force refresh", DabPumpsLogin.ACCESS_TOKEN)

            if method != "Auto":
                context.api._login_info.login_method = method

            _LOGGER.debug(f"Loop test, {idx} of {loop} (success={counter_success}, fail={counter_fail})")
            await asyncio.sleep(60)

    _LOGGER.info(f"Fail summary after {loop} loops:")
    for reason,count in reason_fail.items():
        _LOGGER.info(f"  {count}x {reason}")

    assert counter_fail == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, method, loop, exp_except",
    [
        ("ok",  None,                        0, None),
        ("ok",  DabPumpsLogin.H2D_APP,       0, None),
        ("ok",  DabPumpsLogin.DABLIVE_APP,   0, DabPumpsError),
        ("ok",  DabPumpsLogin.DCONNECT_APP,  0, None),
        ("ok",  DabPumpsLogin.DCONNECT_WEB,  0, DabPumpsError),
        #
        #("24h", None,                        24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.H2D_APP,       24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.DABLIVE_APP,   24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.DCONNECT_APP,  24*60, None),    # Run 1 full day
        #("24h", DabPumpsLogin.DCONNECT_WEB,  24*60, None),    # Run 1 full day
    ]
)
async def test_push_data(name, method, loop, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Try set diagnostics callback function
    context.api.set_diagnostics(lambda context,item,detail,data: None)

    # Login
    await context.api.login(method)

    login_method_org = context.api.login_info.login_method

    # Get install list and details
    await context.api.fetch_install_list()

    install_id = next( (install_id for install_id in context.api.install_map.keys()), None)
    await context.api.fetch_install_details(install_id)

    # Register callback for device state data
    counter_handler: int = 0

    async def device_state_handler(serial: str, state: DabPumpsDeviceState):
        nonlocal counter_handler
        counter_handler += 1

    if context.framework != 'async':
        for device_serial in context.api.device_map.keys():
            with pytest.raises(NotImplementedError):
                await context.api.on_device_state(device_serial, device_state_handler)

    elif exp_except is None:

        for device_serial,device in context.api.device_map.items():
            await context.api.on_device_state(device_serial, device_state_handler)

        # Wait a moment for the Wamp connection to be established and the first data to be received
        await asyncio.sleep(30)

        assert context.api._session_info.dabcs_auth is not None
        assert context.api._session_info.dabcs_device is not None            
        assert context.api._session_info.key is not None
        assert context.api._session_info.wstoken is not None
        assert context.api._wamp_runner_started.is_set()
        assert context.api._wamp_session_started.is_set()
            
        # Do the required iterations
        for idx in range(0,loop+1):

            # Wait for data to come in.
            # Meanwhile keep the api alive
            await context.api.login()

            # Check that data has arrived within each iteration
            assert counter_handler >= idx

            if loop:
                # Simulate failure to recover from
                #if idx % 6 == 0:
                #    await context.api._logout("simulate failure")
                #elif idx % 3 == 0:
                #    await context.api._logout("login force refresh", DabPumpsLogin.ACCESS_TOKEN)

                if method != "Auto":
                    context.api._login_info.login_method = method

                _LOGGER.debug(f"Loop test, {idx} of {loop} (received {counter_handler} state updates")
                await asyncio.sleep(60)

    else:
        for device_serial in context.api.device_map.keys():
            with pytest.raises(exp_except):
                await context.api.on_device_state(device_serial, device_state_handler)
    

@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "method, key, codes, exp_code, exp_except",
    [
        (None,                        "PowerShowerBoost",        ["20","30"],   "=",  None),
        (None,                        "PowerShowerDuration",     ["300","360"], "=",  None),
        (None,                        "SleepModeEnable",         ["0", "1"],    "=",  None),
        (None,                        "Identify",                ["1"],         None, None), # Falls back to None after STATUS_UPDATE_HOLD
        (DabPumpsLogin.H2D_APP,       "PowerShowerBoost",        ["20","30"],   "=",  None),
        (DabPumpsLogin.H2D_APP,       "PowerShowerDuration",     ["300","360"], "=",  None),
        (DabPumpsLogin.H2D_APP,       "SleepModeEnable",         ["0", "1"],    "=",  None),
        (DabPumpsLogin.H2D_APP,       "Identify",                ["1"],         None, None), # Falls back to None after STATUS_UPDATE_HOLD
        (DabPumpsLogin.DABLIVE_APP,   "PowerShowerBoost",        ["20","30"],   "=",  None),
        (DabPumpsLogin.DABLIVE_APP,   "PowerShowerDuration",     ["300","360"], "=",  None),
        (DabPumpsLogin.DABLIVE_APP,   "SleepModeEnable",         ["0", "1"],    "=",  None),
        (DabPumpsLogin.DABLIVE_APP,   "Identify",                ["1"],         None, None), # Falls back to None after STATUS_UPDATE_HOLD
        (DabPumpsLogin.DCONNECT_APP,  "PowerShowerBoost",        ["20","30"],   "=",  None),
        (DabPumpsLogin.DCONNECT_APP,  "PowerShowerDuration",     ["300","360"], "=",  None),
        (DabPumpsLogin.DCONNECT_APP,  "SleepModeEnable",         ["0", "1"],    "=",  None),
        (DabPumpsLogin.DCONNECT_APP,  "Identify",                ["1"],         None, None), # Falls back to None after STATUS_UPDATE_HOLD
        (DabPumpsLogin.DCONNECT_WEB,  "PowerShowerBoost",        ["20","30"],   "=",  None),
        (DabPumpsLogin.DCONNECT_WEB,  "PowerShowerDuration",     ["300","360"], "=",  None),
        (DabPumpsLogin.DCONNECT_WEB,  "SleepModeEnable",         ["0", "1"],    "=",  None),
        (DabPumpsLogin.DCONNECT_WEB,  "Identify",                ["1"],         None, None), # Falls back to None after STATUS_UPDATE_HOLD
    ]
)
async def test_set_data_by_code(method, key, codes, exp_code, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Login and get install list
    await context.api.login(method)
    await context.api.fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    # Get install details, metadata and initial statuses
    for install_id in context.api.install_map:
        await context.api.fetch_install_details(install_id)

    # Resolve device for this key (via config as it may not be found in state)
    for serial,device in context.api.device_map.items():
        config = context.api.device_config_map.get(device.config_id)
        param = config.meta_params.get(key)
        if param is not None:
            break
    
    assert serial is not None
    assert device is not None
    assert param is not None

    # Check config param
    install = context.api.install_map.get(device.install_id)

    if install.role not in param.change:
        # Not allowed to change this param with this user account. Skip test
        _LOGGER.debug(f"User '{TEST_USERNAME}' is not allowed to set {key}. Skip test")
        return

    # Find current code and value and find a new code to change into
    old_status = context.api.get_status_value(serial,key)
    old_code = old_status.code if old_status is not None else None
    new_code = next( (code for code in codes if code != old_code), None )

    # Change device status and do immediate test of changed value. 
    # We hold the changed value while the backend is processing the change.
    changed = await context.api.change_device_status(serial, key, code=new_code)
    if changed:
        await context.api.fetch_install_statuses(install_id)

        status = context.api.get_status_value(serial, key)
        update_ts = context.api.get_status_update(serial, key)

        assert status is None or status.code == new_code 
        assert update_ts is not None

        _LOGGER.debug(f"Found value changed from {old_code} to {new_code}")

        # Wait until the backend has processed the change and test again
        _LOGGER.debug(f"Wait for DAB Servers to process the change")
        await asyncio.sleep(40)
        await context.api.login()

    # Test after change has been processed by backend
    await context.api.fetch_install_statuses(install_id)

    status = context.api.get_status_value(serial, key)
    update_ts = context.api.get_status_update(serial, key)

    assert status is None or status.code == new_code 
    assert update_ts is None

    _LOGGER.debug(f"Found value still changed from {old_code} to {new_code}")

    # Change back to original value and do immediate test of changed value
    if old_status is None:
        return  # button type, no need to revert back
    
    changed = await context.api.change_device_status(status.serial, status.key, code=old_code)
    if changed:
        await context.api.fetch_install_statuses(install_id)

        status = context.api.get_status_value(serial, key)
        update_ts = context.api.get_status_update(serial, key)

        assert status is None or status.code == old_code
        assert update_ts is not None

        _LOGGER.debug(f"Found value changed back from {new_code} to {old_code}")


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "method, key, lang, exp_value, exp_except",
    [
        (None, "SleepModeEnable",    "en", "=", None),
        (None, "SleepModeEnable",    "nl", "=", None),
    ]
)
async def test_set_data_by_value(method, key, lang, exp_value, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Login and get install list
    await context.api.login(method)
    await context.api.fetch_strings(lang)
    await context.api.fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    # Get install details, metadata and initial statuses
    for install_id in context.api.install_map:
        await context.api.fetch_install_details(install_id)

    # Resolve device for this key (via config as it may not be found in state)
    for serial,device in context.api.device_map.items():
        config = context.api.device_config_map.get(device.config_id)
        param = config.meta_params.get(key)
        if param is not None:
            break
    
    assert serial is not None
    assert device is not None
    assert param is not None

    # Check config param
    install = context.api.install_map.get(device.install_id)

    if install.role not in param.change:
        # Not allowed to change this param with this user account. Skip test
        _LOGGER.debug(f"User '{TEST_USERNAME}' is not allowed to set {key}. Skip test")
        return

    # Find current code and value and find a new code to change into
    old_status = context.api.get_status_value(serial, key)
    old_value = old_status.value if old_status else None
    new_value = next( (val for key,val in param.values.items() if val != old_value), None )

    # Change device status and do immediate test of changed value. 
    # We hold the changed value while the backend is processing the change.
    changed = await context.api.change_device_status(serial, key, value=new_value)
    if changed:
        await context.api.fetch_install_statuses(install_id)

        status = context.api.get_status_value(serial, key)
        update_ts = context.api.get_status_update(serial, key)
    
        assert status is None or status.value == new_value
        assert update_ts is not None

        _LOGGER.debug(f"Found value changed from {old_value} to {new_value}")

        # Wait until the backend has processed the change and test again
        _LOGGER.debug(f"Wait for DAB Servers to process the change")
        await asyncio.sleep(40)
        await context.api.login()

    # Test after change has been processed by backend
    await context.api.fetch_install_statuses(install_id)

    status = context.api.get_status_value(serial, key)
    update_ts = context.api.get_status_update(serial, key)

    assert status is None or status.value == new_value
    assert update_ts is not None

    _LOGGER.debug(f"Found value still changed from {old_value} to {new_value}")

    # Change back to original value and do immediate test of changed value
    if old_status is None:
        return  # button type, no need to revert back
    
    changed = await context.api.change_device_status(status.serial, status.key, value=old_value)
    if changed:
        await context.api.fetch_install_statuses(install_id)

        status = context.api.get_status_value(serial, key)
        update_ts = context.api.get_status_update(serial, key)

        assert status is None or status.value == old_value
        assert update_ts is not None

        _LOGGER.debug(f"Found value changed back from {new_value} to {old_value}")


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "method, exp_except",
    [
        (None,                        None),
        (DabPumpsLogin.H2D_APP,       None),
        (DabPumpsLogin.DABLIVE_APP,   None),
        (DabPumpsLogin.DCONNECT_APP,  None),
        (DabPumpsLogin.DCONNECT_WEB,  None),
    ]
)
async def test_set_role(method, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Login and get install list
    await context.api.login(method)
    await context.api.fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    # Get first install details, metadata and initial statuses
    install = next( (install for install in context.api.install_map.values()), None)
    assert install is not None
    install_id = install.id

    # Find current role and determine new role to change into
    old_role = install.role
    new_role = next( (role for role in [DabPumpsUserRole.CUSTOMER,DabPumpsUserRole.INSTALLER] if role != old_role), None )

    # Change role and do immediate test of changed value. 
    # We hold the changed value while the backend is processing the change.
    changed = await context.api.change_install_role(install_id, old_role, new_role)
    if changed:
        await context.api.fetch_install_list()

        install = next( (install for install in context.api.install_map.values() if install.id == install_id), None)
        assert install is not None
        assert install.role == new_role
        _LOGGER.debug(f"Found role changed from {old_role} to {new_role}")

        # Wait until the backend has processed the change and test again
        _LOGGER.debug(f"Wait for DAB Servers to process the change")
        await asyncio.sleep(40)
        await context.api.login()

    # Test after change has been processed by backend
    await context.api.fetch_install_list()

    install = next( (install for install in context.api.install_map.values() if install.id == install_id), None)
    assert install is not None
    assert install.role == new_role
    _LOGGER.debug(f"Found role still changed from {old_role} to {new_role}")

    # Change back to original value and do immediate test of changed value
    changed = await context.api.change_install_role(install_id, new_role, old_role)
    if changed:
        await context.api.fetch_install_list()

        install = next( (install for install in context.api.install_map.values() if install.id == install_id), None)
        assert install is not None
        assert install.role == old_role
        _LOGGER.debug(f"Found role changed back from {new_role} to {old_role}")


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, lang, exp_lang",
    [
        ("strings en", 'en', 'en'),
        ("strings nl", 'nl', 'nl'),
        ("strings xx", 'xx', 'en'),
    ]
)
async def test_strings(name, lang, exp_lang, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps("dummy_usr", "wrong_pwd") # no login needed

    # Get strings
    await context.api.fetch_strings(lang)

    assert context.api.string_map is not None
    assert type(context.api.string_map) is dict
    assert len(context.api.string_map) > 0

    assert context.api.string_map_lang == exp_lang


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, method, exp_d, exp_except",
    [
        ("ok",  None,                        3, None),
        ("ok",  DabPumpsLogin.H2D_APP,       3, None),
        ("ok",  DabPumpsLogin.DABLIVE_APP,   1, None),
        ("ok",  DabPumpsLogin.DCONNECT_APP,  1, None),
        ("ok",  DabPumpsLogin.DCONNECT_WEB,  2, None),
    ]
)
async def test_callbacks(name, method, exp_d, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Set diagnostics callback functions
    counter_diagnostics = 0

    def diagnostics_updated(context,item,detail,data): 
        nonlocal counter_diagnostics
        counter_diagnostics += 1

    context.api.set_diagnostics(callback=diagnostics_updated)

    # Login
    await context.api.login(method)

    assert context.api.login_active
    assert context.api.login_info.login_method is not None
    assert counter_diagnostics == exp_d

    # Do some more api calls; shouldn't change info and token counters since tokens are still valid
    await context.api.fetch_install_list()

    assert counter_diagnostics == exp_d + 1

    # Get first install details, metadata and initial statuses
    install = next( (install for install in context.api.install_map.values()), None)
    assert install is not None
    install_id = install.id
    
    # Repeat the login; shouldn't change info and token counters since tokens are still valid
    await context.api.login()
    
    assert counter_diagnostics >= exp_d + 2

    # Do some more api calls; shouldn't change info and token counters since tokens are still valid
    await context.api.fetch_install_details(install_id)

    assert counter_diagnostics >= exp_d + 3


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, method, exp_except",
    [
        ("ok",  None,                        None),
        ("ok",  DabPumpsLogin.H2D_APP,       None),
        ("ok",  DabPumpsLogin.DABLIVE_APP,   None),
        ("ok",  DabPumpsLogin.DCONNECT_APP,  None),
        # ("ok",  DabPumpsLogin.DCONNECT_WEB,  None), Skipped because access and refresh tokens are handled via cookies
    ]
)
async def test_token_reuse(name, method, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Set login info, token and diagnostics callback functions
    login_info = None
    access_token_info = None
    refresh_token_info = None

    # Login
    await context.api.login(method)

    assert context.api.login_active
    assert context.api.login_info.login_method is not None
    assert context.api.access_token_info is not None
    assert context.api.refresh_token_info is not None

    # Do some more api calls
    await context.api.fetch_install_list()
    
    # Remember the login info, then close the api
    login_info = context.api.login_info
    access_token_info = context.api.access_token_info
    refresh_token_info = context.api.refresh_token_info

    await context.api.close()
    await asyncio.sleep(10)

    # Create a fresh api instance, passing info, access and refresh token and repeat the login. 
    # Should not do an actual new login, nor a refresh of the access token
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD, login_info=login_info, access_token_info=access_token_info, refresh_token_info=refresh_token_info)
    await context.api.login()
    await context.api.fetch_install_list()

    assert context.api.login_active
    assert context.api.login_info == login_info
    assert context.api.access_token_info == access_token_info
    assert context.api.refresh_token_info == refresh_token_info

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0
    
    await context.api.close()
    await asyncio.sleep(10)

    # Create a fresh api instance, passing info and refresh token (but not acces token) and repeat the login. 
    # Should not do an actual new login, only a refresh of the access token
    context.api = AsyncDabPumps(TEST_USERNAME, TEST_PASSWORD, login_info=login_info, refresh_token_info=refresh_token_info)
    await context.api.login()
    await context.api.fetch_install_list()

    assert context.api.login_active
    assert context.api.login_info == login_info
    assert context.api.access_token_info != access_token_info
    assert context.api.refresh_token_info != refresh_token_info

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0


@pytest.mark.parametrize(
    "name, attr, exp_id",
    [
        ("multi", ['abc', 'DEF', '123'], 'abc_def_123'),
        ("spaces", ['abc DEF', '123'], 'abc_def_123'),
        ("underscore", ['abc_DEF', '123'], 'abc_def_123'),
        ('ignored start', ['@%^_DEF', '123'], '_def_123'),
        ('ignored mid', ['@bc_DE#', '123'], 'bc_de_123'),
        ('ignored end', ['abc_DEF', '!&'], 'abc_def_'),
    ]
)
def test_create_id(name, attr, exp_id, request):

    id = AsyncDabPumps.create_id(*attr)
    assert id == exp_id


@pytest_asyncio.fixture
async def device_map():
    device_map = {
        "SERIAL": DabPumpsDevice(
            id = 'DEVICE ID',
            serial = 'SERIAL',
            name = 'test device',
            product = 'test product',
            vendor = 'DAB Pumps',
            hw_version = 'test hw version',
            config_id = 'CONFIG_ID',
            install_id = 'INSTALL_ID',
            sw_version = 'test sw version',
            mac_address = 'test mac',
        ),
    }
    yield device_map

@pytest_asyncio.fixture
async def config_map():
    config_map = {
        "CONFIG_ID": DabPumpsDeviceConfig(
            id = 'CONFIG_ID',
            label = 'test label',
            description = 'test description',
            meta_params = {
                "KEY_ENUM":  DabPumpsParams(name='NameEnum',  type=DabPumpsParamType.ENUM,    unit=None, weight=None, values={'1':'one', '2':'two', '3':'three'}, min=1, max=3, family='f', group='g', view='CSIR', change=''),
                "KEY_FLOAT": DabPumpsParams(name='NameFloat', type=DabPumpsParamType.MEASURE, unit='F',  weight=0.1,  values=None, min=0, max=1,  family='f', group='g', view='CSIR', change=''),
                "KEY_INT":   DabPumpsParams(name='NameInt',   type=DabPumpsParamType.MEASURE, unit='I',  weight=1,    values=None, min=0, max=10, family='f', group='g', view='CSIR', change=''),
                "KEY_LABEL": DabPumpsParams(name='NameLabel', type=DabPumpsParamType.LABEL,   unit='',   weight=None, values=None, min=0, max=0,  family='f', group='g', view='CSIR', change=''),
            }
        ),
    }
    yield config_map

@pytest_asyncio.fixture
async def state_map():
    state_map = {
        'SERIAL': DabPumpsDeviceState(
            status_ts = utcnow(),
            status = {
                'KEY_ENUM':  DabPumpsStatus(code='1', value='one'),
                'KEY_FLOAT': DabPumpsStatus(code='1', value=0.1),
                'KEY_INT':   DabPumpsStatus(code='1', value=1),
                'KEY_LABEL': DabPumpsStatus(code='ABC', value='ABC'),
            },
        )
    }
    yield state_map

@pytest_asyncio.fixture
async def string_map():
    string_map = {
        'one': 'een',
        'two': 'twee',
        'three': 'drie',
        'ABC': 'aa bee cee',
    }
    yield string_map


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map")
@pytest.mark.parametrize(
    "name, serial, key, code, exp_value",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', '2', ('2', '')),
        ("key unknown", 'SERIAL', 'KEY_XX', '2', ('2', '')),
        ("enum ok", "SERIAL", 'KEY_ENUM', '2', ('two', None)),
        ("enum no", "SERIAL", 'KEY_ENUM', '4', ('4', None)),
        ("enum no", "SERIAL", 'KEY_ENUM', '4', ('4', None)),
        ("float ok", "SERIAL", 'KEY_FLOAT', '2', (0.2, 'F')),
        ("float min", "SERIAL", 'KEY_FLOAT', '-1', (-0.1, 'F')),
        ("float max", "SERIAL", 'KEY_FLOAT', '11', (1.1, 'F')),
        ("int ok", "SERIAL", 'KEY_INT', '2', (2, 'I')),
        ("int min", "SERIAL", 'KEY_INT', '-1', (-1, 'I')),
        ("int max", "SERIAL", 'KEY_INT', '11', (11, 'I')),
        ("label ok", "SERIAL", 'KEY_LABEL', 'ABC', ('ABC', '')),
    ]
)
async def test_decode(name, serial, key, code, exp_value, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._device_config_map = request.getfixturevalue("config_map")

    value = context.api._decode_status_value(serial, key, code)
    assert value == exp_value
    assert type(value) == type(exp_value)


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map")
@pytest.mark.parametrize(
    "name, serial, key, value, exp_code",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', 'two', 'two'),
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', 'two', 'two'),
        ("key unknown", 'SERIAL', 'KEY_XX', 'two', 'two'),
        ("enum ok", "SERIAL", 'KEY_ENUM', 'two', '2'),
        ("enum no", "SERIAL", 'KEY_ENUM', 'four', 'four'),
        ("float ok", "SERIAL", 'KEY_FLOAT', 0.2, '2'),
        ("float min", "SERIAL", 'KEY_FLOAT', -0.1, '-1'),
        ("float max", "SERIAL", 'KEY_FLOAT', 1.1, '11'),
        ("int ok", "SERIAL", 'KEY_INT', 2, '2'),
        ("int min", "SERIAL", 'KEY_INT', -1, '-1'),
        ("int max", "SERIAL", 'KEY_INT', 11, '11'),
        ("label ok", "SERIAL", 'KEY_LABEL', 'ABC', 'ABC'),
    ]
)
async def test_encode(name, serial, key, value, exp_code, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._device_config_map = request.getfixturevalue("config_map")

    code = context.api._encode_status_value(serial, key, value)
    assert code == exp_code
    assert type(code) == type(exp_code)


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map", "state_map", "string_map")
@pytest.mark.parametrize(
    "name, serial, key, exp_code, exp_value",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', None, None),
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', None, None),
        ("key unknown", 'SERIAL', 'KEY_XX', None, None),
        ("enum ok", "SERIAL", 'KEY_ENUM', '1', 'one'),
        ("float ok", "SERIAL", 'KEY_FLOAT', '1', 0.1),
        ("int ok", "SERIAL", 'KEY_INT', '1', 1),
        ("label ok", "SERIAL", 'KEY_LABEL', 'ABC', 'ABC'),
    ]
)
async def test_status(name, serial, key, exp_code, exp_value, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._device_config_map = request.getfixturevalue("config_map")
    context.api._device_state_map = request.getfixturevalue("state_map")
    context.api._string_map = request.getfixturevalue("string_map")

    status = context.api.get_status_value(serial, key)
    if exp_code is None:
        assert status is None
    else:
        assert status is not None
        assert status.code == exp_code
        assert status.value == exp_value


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map", "state_map", "string_map")
@pytest.mark.parametrize(
    "name, serial, key, exp_type, exp_values, exp_unit",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', None, None, None),
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', None, None, None),
        ("key unknown", 'SERIAL', 'KEY_XX', None, None, None),
        ("enum ok", "SERIAL", 'KEY_ENUM', DabPumpsParamType.ENUM, {'1':'one', '2':'two', '3':'three'}, None),
        ("float ok", "SERIAL", 'KEY_FLOAT', DabPumpsParamType.MEASURE, None, 'F'),
        ("int ok", "SERIAL", 'KEY_INT', DabPumpsParamType.MEASURE, None, 'I'),
        ("label ok", "SERIAL", 'KEY_LABEL', DabPumpsParamType.LABEL, None, ''),
    ]
)
async def test_metadata(name, serial, key, exp_type, exp_values, exp_unit, request):
    context = request.getfixturevalue("context")
    context.api = AsyncDabPumps("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._device_config_map = request.getfixturevalue("config_map")
    context.api._device_state_map = request.getfixturevalue("state_map")
    context.api._string_map = request.getfixturevalue("string_map")

    params = context.api.get_status_metadata(serial, key)
    if exp_type is None:
        assert params is None
    else:
        assert params is not None
        assert params.type == exp_type
        assert params.unit == exp_unit

        if exp_values is None:
            assert params.values is None
        else:
            assert params.values is not None
            assert len(params.values) == len(exp_values)
            for k,v in exp_values.items():
                assert k in params.values
                assert params.values[k] == v
