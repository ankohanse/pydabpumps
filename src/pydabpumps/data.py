from datetime import date, datetime
import logging
import secrets

from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from types import MappingProxyType, NoneType
from typing import Any, ClassVar, Iterable, Mapping, Set

from .const import (
    DABCS_API_DOMAIN,
    DABLIVE_APP_DABCS_AUTH,
    DABLIVE_APP_USER_AGENT,
    DCONNECT_API_DOMAIN,
    DCONNECT_APP_DABCS_AUTH,
    DCONNECT_APP_USER_AGENT,
    DCONNECT_WEB_DABCS_AUTH,
    H2D_APP_DABCS_AUTH,
    H2D_APP_USER_AGENT,
    utcnow,
    utcmin,
)

_LOGGER = logging.getLogger(__name__)


class DabPumpsError(Exception):
    """Exception to indicate generic error failure."""    

class DabPumpsLoginAbortedError(DabPumpsError):
    """
    Exception to indicate that login was aborted. Reasons could be:
    - a rate-limit was applied during login or token refresh
    - an error occurred but the refresh token itself is still assumed valid.
    """

class DabPumpsConnectError(DabPumpsError):
    """Exception to indicate authentication failure."""

class DabPumpsAuthError(DabPumpsError):
    """Exception to indicate authentication or authorization failure."""

class DabPumpsDataError(DabPumpsError):
    """Exception to indicate generic data failure."""  


class DabPumpsApiFlag(StrEnum):
    """Extra flags to pass to Api"""
    IGNORE_RATE_LIMIT   = "IGNORE_RATE_LIMIT"   # bool

class DabPumpsLogin(StrEnum):
    ACCESS_TOKEN = 'Access-Token'
    REFRESH_TOKEN = 'Refresh-Token'
    H2D_APP = 'H2D-app'                 # Uses DabCS with Authorization Header
    DABLIVE_APP = 'DabLive-app'         # Uses DConnect with Authorization Header
    DCONNECT_APP = 'DConnect-app'       # Uses DConnect with Authorization Header
    DCONNECT_WEB = 'DConnect-web'       # Uses DConnect with Cookie

class DabPumpsFetch(StrEnum):
    DABCS = DABCS_API_DOMAIN,
    DCONNECT = DCONNECT_API_DOMAIN

class DabPumpsAuth(StrEnum):
    HEADER = "Authorization Header"
    COOKIE = "Cookie"


class DabPumpsUserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    CUSTOMER_PRO = "CUSTOMER-PRO"
    CUSTOMER_FREE = "CUSTOMER_FREE"
    INSTALLER = "INSTALLER"
    INSTALLER_FREE = "INSTALLER_FREE"
    LOCAL_INSTALLER = "LOCALINSTALLER"
    LOCAL_CONFIG = "LOCALCONFIG"
    SERVICE = "SERVICE"
    R_AND_D = "R&D"


class DabPumpsParamType(StrEnum):
    ENUM = "enum"
    MEASURE = "measure"
    LABEL = "label"
    SETTINGS = "settings"


class DabPumpsStatusCode(StrEnum):
    DISABLED = "d"
    HIDDEN = "h"


@dataclass
class DabPumpsInstall:
    id: str
    name: str
    description: str = None
    company: str = None
    address: str = None
    role: DabPumpsUserRole = DabPumpsUserRole.CUSTOMER
    subscr_ts: datetime|None = None # utc
    devices: int = 0

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        status = DabPumpsStatus(**dict)
        """
        if self.subscr_ts and isinstance(self.subscr_ts, str):
            self.subscr_ts = datetime.fromisoformat(self.subscr_ts)


@dataclass
class DabPumpsDevice:
    id: str
    serial: str
    name: str
    vendor: str
    product: str
    hw_version: str
    sw_version: str
    mac_address: str
    config_id: str
    install_id: str


@dataclass
class DabPumpsParams:
    name: str
    type: DabPumpsParamType
    unit: str
    weight: float|None
    values: dict[str,str]|None
    min: float|None
    max: float|None
    family: str
    group: str
    view: list[DabPumpsUserRole]
    change: list[DabPumpsUserRole]


@dataclass
class DabPumpsDeviceConfig:
    id: str
    label: str
    description: str
    meta_params: dict[str, DabPumpsParams]

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        status = DabPumpsDeviceConfig(**dict)
        """
        for meta_key in self.meta_params:
            meta_param = self.meta_params[meta_key]

            if meta_param and isinstance(meta_param, dict):
                self.meta_params[meta_key] = DabPumpsParams(**meta_param)


@dataclass
class DabPumpsStatus:
    code: str
    value: str


@dataclass
class DabPumpsDeviceState:
    status: dict[str, DabPumpsStatus]
    status_ts: datetime = None # utc
    lastrecv_ts: datetime = None # utc
    online: bool = True
    state: str = None   # Note: only updated in fetch_install_statuses, not from push data

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        state = DabPumpsDeviceState(**dict)
        """
        if self.status_ts and isinstance(self.status_ts, str):
            self.status_ts = datetime.fromisoformat(self.status_ts)

        if self.lastrecv_ts and isinstance(self.lastrecv_ts, str):
            self.lastrecv_ts = datetime.fromisoformat(self.lastrecv_ts)

        for item_key in self.status:
            item_status = self.status[item_key]

            if item_status and isinstance(item_status, dict):
                self.status[item_key] = DabPumpsStatus(**item_status)


@dataclass
class DabPumpsLoginInfo:
    login_method: DabPumpsLogin = None

    retry_schedule: datetime = utcmin()
    retry_count: int = 0

    _dabcs_device: ClassVar[str] = secrets.token_hex(8)  # Static class variable, never to be changed after init

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        info = DabPumpsLoginInfo(**dict)
        """
        if self.retry_schedule and isinstance(self.retry_schedule, str):
            self.retry_schedule = datetime.fromisoformat(self.retry_schedule)

    @property
    def fetch_method(self) -> DabPumpsFetch:
        match self.login_method:
            case None:                  return None
            case DabPumpsLogin.H2D_APP: return DabPumpsFetch.DABCS
            case _:                     return DabPumpsFetch.DCONNECT

    @property
    def auth_method(self) -> DabPumpsAuth:
        match self.login_method:
            case None:                       return None
            case DabPumpsLogin.DCONNECT_WEB: return DabPumpsAuth.COOKIE
            case _:                          return DabPumpsAuth.HEADER
    
    @property
    def extra_headers(self) -> dict[str,str]:
        match self.login_method:
            case None:                       return {}
            case DabPumpsLogin.H2D_APP:      return { 'User-Agent': H2D_APP_USER_AGENT }
            case DabPumpsLogin.DABLIVE_APP:  return { 'User-Agent': DABLIVE_APP_USER_AGENT }
            case DabPumpsLogin.DCONNECT_APP: return { "User-Agent": DCONNECT_APP_USER_AGENT }
            case DabPumpsLogin.DCONNECT_WEB: return { "User-Agent": DCONNECT_APP_USER_AGENT }
            case _:                          return {}

    @property
    def dabcs_auth(self) -> str:
        match self.login_method:
            case None:                       return None
            case DabPumpsLogin.H2D_APP:      return H2D_APP_DABCS_AUTH
            case DabPumpsLogin.DABLIVE_APP:  return DABLIVE_APP_DABCS_AUTH
            case DabPumpsLogin.DCONNECT_APP: return DCONNECT_APP_DABCS_AUTH
            case DabPumpsLogin.DCONNECT_WEB: return DCONNECT_WEB_DABCS_AUTH
            case _:                          return None

    @property
    def dabcs_device(self) -> str:
        return self._dabcs_device


@dataclass
class DabPumpsAccessTokenInfo:
    token: str = None
    expires_in: int = None # seconds
    expiry: datetime = None #utc

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        info = DabPumpsAccessTokenInfo(**dict)
        """
        if self.expiry and isinstance(self.expiry, str):
            self.expiry = datetime.fromisoformat(self.expiry)

    @property
    def is_valid(self):
        return self.token is not None and self.expiry is not None and utcnow() < self.expiry


@dataclass
class DabPumpsRefreshTokenInfo:
    token: str = None
    expires_in: int = None # seconds
    expiry: datetime = None # utc
    client_id: str = None
    client_secret: str = None

    retry_schedule: datetime = utcmin()
    retry_count: int = 0

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        info = DabPumpsRefreshTokenInfo(**dict)
        """
        if self.expiry and isinstance(self.expiry, str):
            self.expiry = datetime.fromisoformat(self.expiry)

        if self.retry_schedule and isinstance(self.retry_schedule, str):
            self.retry_schedule = datetime.fromisoformat(self.retry_schedule)


@dataclass
class DabPumpsSessionInfo:
    key: str = None
    wstoken: str = None

    # for diagnostics
    leave_reasons: set[str] = field(default_factory=set)


@dataclass
class DabPumpsHistoryItem:
    ts: datetime
    op: str
    rsp: str|None = None
 
    @staticmethod
    def create(timestamp: datetime, context: str , request: dict|None, response: dict|None, token: dict|None) -> 'DabPumpsHistoryItem':
        item = DabPumpsHistoryItem( 
            ts = timestamp, 
            op = context,
        )

        # If possible, add a summary of the response status and json res and code
        if response:
            rsp_parts = []
            if "status_code" in response:
                rsp_parts.append(response["status_code"])
            if "status" in response:
                rsp_parts.append(response["status"])
            if "method" in response:
                rsp_parts.append(response["method"])
            
            if json := response.get("json"):
                if res := json.get('res') or '': rsp_parts.append(f"res={res}")
                if code := json.get('code') or '': rsp_parts.append(f"code={code}")
                if msg := json.get('msg') or '': rsp_parts.append(f"msg={msg}")
                if details := json.get('details') or '': rsp_parts.append(f"details={details}")

            item.rsp = ', '.join(rsp_parts)

        return item


@dataclass
class DabPumpsHistoryDetail:
    ts: datetime
    req: dict|None
    rsp: dict|None
    token: dict|None

    @staticmethod
    def create(timestamp: datetime, context: str , request: dict|None, response: dict|None, token: dict|None) -> 'DabPumpsHistoryDetail':
        detail = DabPumpsHistoryDetail(
            ts = timestamp, 
            req = request,
            rsp = response,
            token = token,
        )
        return detail


DATACLASSES_EXCLUDE_NONE = (DabPumpsHistoryItem, DabPumpsHistoryDetail)


def to_dict(obj: Any, flags:set[str]=None) -> Any:
        """
        Recursive to dictionary handler that is aware of dataclasses and Mapping proxies at any level in the data structure
        """
        # Sanity check
        if flags is None:
            flags = set()

        try:
            if isinstance(obj, (int,float,str,NoneType)):
                return obj
            
            elif isinstance(obj, (datetime, date)):
                return obj.isoformat()
            
            elif is_dataclass(obj):
                # Not using dataclass.asdict() method, because it does not recurse in to the dataclass field values
                # and convert the values themselves to dicts.
                
                flags_inner = flags if not isinstance(obj, DATACLASSES_EXCLUDE_NONE) else flags | {"exclude_none_values"}
                result = []
                for f in fields(obj):
                    value = to_dict(getattr(obj, f.name), flags_inner)
                    result.append((f.name, value))

                if 'exclude_none_values' in flags_inner:
                    return { k: v for (k, v) in result if v is not None }
                else:
                    return dict(result)
                
            elif isinstance(obj, (list,set,tuple)):
                if hasattr(obj, '_fields'):
                    # namedtuple, Standard asdict will not recurse in to the namedtuple fields and convert them to dicts (using dict_factory).
                    if 'exclude_none_values' in flags:
                        return type(obj)( *[to_dict(v, flags) for v in obj if v is not None] )
                    else:
                        return type(obj)( *[to_dict(v, flags) for v in obj] )
                else:
                    # standard list, set or tuple
                    if 'exclude_none_values' in flags:
                        return type(obj)( to_dict(v, flags) for v in obj if v is not None )
                    else:
                        return type(obj)( to_dict(v, flags) for v in obj )
            
            elif isinstance(obj, dict):
                if hasattr(type(obj), 'default_factory'):
                    # defaultdict has a different constructor from dict
                    result = type(obj)(getattr(obj, 'default_factory'))
                else:
                    result = type(obj)()
            
                for k, v in obj.items():
                    if v is not None or not 'exclude_none_values' in flags:
                        result[k] = to_dict(v, flags)
                return result
            
            elif isinstance(obj, (Mapping, MappingProxyType)):
                 return to_dict(dict(obj), flags)
            
            else:
                return f"{type(obj)} {obj}"
            
        except Exception as ex:
            return f"Could not serialize type {type(obj)}: {ex}"
        

