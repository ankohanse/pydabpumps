from datetime import datetime
import logging

from dataclasses import dataclass
from enum import StrEnum

from .const import (
    DABCS_API_DOMAIN,
    DCONNECT_API_DOMAIN,
    DCONNECT_APP_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class DabPumpsError(Exception):
    """Exception to indicate generic error failure."""    
    
class DabPumpsConnectError(DabPumpsError):
    """Exception to indicate authentication failure."""

class DabPumpsAuthError(DabPumpsError):
    """Exception to indicate authentication or authorization failure."""

class DabPumpsDataError(DabPumpsError):
    """Exception to indicate generic data failure."""  


class DabPumpsLogin(StrEnum):
    ACCESS_TOKEN = 'Access-Token'
    REFRESH_TOKEN = 'Refresh-Token'
    H2D_APP = 'H2D-app'                 # Uses DabCS with Authorization Header
    DABLIVE_APP_0 = 'DabLive-app_0'     # Uses DConnect with Authorization Header
    DABLIVE_APP_1 = 'DabLive-app_1'     # Uses DConnect with Authorization Header
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
    CUSTOMER_FREE = "CUSTOMER_FREE"
    INSTALLER = "INSTALLER"
    INSTALLER_FREE = "INSTALLER_FREE"
    INSTALLER_LOCAL = "LOCALINSTALLER"
    SERVICE = "SERVICE"
    R_AND_D = "R&D"

    @staticmethod
    def to_char(role: str):
        match role:
            case DabPumpsUserRole.CUSTOMER: return 'C'
            case DabPumpsUserRole.CUSTOMER_FREE: return 'c'
            case DabPumpsUserRole.INSTALLER: return 'I'
            case DabPumpsUserRole.INSTALLER_FREE: return 'i'
            case DabPumpsUserRole.INSTALLER_LOCAL: return 'L'
            case DabPumpsUserRole.SERVICE: return 'S'
            case DabPumpsUserRole.R_AND_D: return 'R'
            case _: return 'C'


class DabPumpsParamType(StrEnum):
    ENUM = "enum"
    MEASURE = "measure"
    LABEL = "label"


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
    key: str
    name: str
    type: DabPumpsParamType
    unit: str
    weight: float|None
    values: dict[str,str]|None
    min: float|None
    max: float|None
    family: str
    group: str
    view: str
    change: str
    log: str
    report: str


@dataclass
class DabPumpsConfig:
    id: str
    label: str
    description: str
    meta_params: dict[str, DabPumpsParams]

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        status = DabPumpsConfig(**dict)
        """
        for meta_key in self.meta_params:
            meta_param = self.meta_params[meta_key]

            if meta_param and isinstance(meta_param, dict):
                self.meta_params[meta_key] = DabPumpsParams(**meta_param)


@dataclass
class DabPumpsStatus:
    serial: str
    key: str
    name: str
    code: str
    value: str
    unit: str
    status_ts: datetime|None # utc
    update_ts: datetime|None # utc

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        status = DabPumpsStatus(**dict)
        """
        if self.status_ts and isinstance(self.status_ts, str):
            self.status_ts = datetime.fromisoformat(self.status_ts)

        if self.update_ts and isinstance(self.update_ts, str):
            self.update_ts = datetime.fromisoformat(self.update_ts)


class DabPumpsLogin(StrEnum):
    ACCESS_TOKEN = 'Access-Token'
    REFRESH_TOKEN = 'Refresh-Token'
    H2D_APP = 'H2D-app'                 # Uses DabCS with Authorization Header
    DABLIVE_APP_0 = 'DabLive-app_0'     # Uses DConnect with Authorization Header
    DABLIVE_APP_1 = 'DabLive-app_1'     # Uses DConnect with Authorization Header
    DCONNECT_APP = 'DConnect-app'       # Uses DConnect with Authorization Header
    DCONNECT_WEB = 'DConnect-web'       # Uses DConnect with Cookie

class DabPumpsFetch(StrEnum):
    DABCS = DABCS_API_DOMAIN,
    DCONNECT = DCONNECT_API_DOMAIN

class DabPumpsAuth(StrEnum):
    HEADER = "Authorization Header"
    COOKIE = "Cookie"


@dataclass
class DabPumpsLoginInfo():
    login_method: DabPumpsLogin = None

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
            case None:                       return None
            case DabPumpsLogin.DCONNECT_WEB: return { "User-Agent": DCONNECT_APP_USER_AGENT }
            case _:                          return {}


@dataclass
class DabPumpsAccessTokenInfo():
    token: str = None
    expiry: datetime = None

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        info = DabPumpsAccessTokenInfo(**dict)
        """
        if self.expiry and isinstance(self.expiry, str):
            self.expiry = datetime.fromisoformat(self.expiry)


@dataclass
class DabPumpsRefreshTokenInfo():
    token: str = None
    expiry: datetime = None
    client_id: str = None
    client_secret: str = None

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        info = DabPumpsRefreshTokenInfo(**dict)
        """
        if self.expiry and isinstance(self.expiry, str):
            self.expiry = datetime.fromisoformat(self.expiry)


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


class DabPumpsDictFactory:
    @staticmethod
    def exclude_none_values(x):
        """
        Usage:
          item = DabPumpsHistoryItem(...)
          item_as_dict = asdict(item, dict_factory=DabPumpsDictFactory.exclude_none_values)
        """
        return { k: v for (k, v) in x if v is not None }

