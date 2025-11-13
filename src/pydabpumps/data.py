from datetime import datetime
import logging

from dataclasses import dataclass
from enum import StrEnum


_LOGGER = logging.getLogger(__name__)


class DabPumpsError(Exception):
    """Exception to indicate generic error failure."""    
    
class DabPumpsConnectError(DabPumpsError):
    """Exception to indicate authentication failure."""

class DabPumpsAuthError(DabPumpsError):
    """Exception to indicate authentication or authorization failure."""

class DabPumpsDataError(DabPumpsError):
    """Exception to indicate generic data failure."""  


class DabPumpsUserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    INSTALLER = "INSTALLER"

class DabPumpsParamType(StrEnum):
    ENUM = "enum"
    MEASURE = "measure"
    LABEL = "label"


@dataclass
class DabPumpsInstall:
    id: str
    name: str
    description: str
    company: str
    address: str
    role: DabPumpsUserRole
    devices: int


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
    status_ts: datetime|None
    update_ts: datetime|None

    def __post_init__(self):
        """
        Custom processing in case the dataclass was constructed from a dict
        status = DabPumpsStatus(**dict)
        """
        if self.status_ts and isinstance(self.status_ts, str):
            self.status_ts = datetime.fromisoformat(self.status_ts)

        if self.update_ts and isinstance(self.update_ts, str):
            self.update_ts = datetime.fromisoformat(self.update_ts)


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
            
            if json := response.get("json", None):
                if res := json.get('res', ''): rsp_parts.append(f"res={res}")
                if code := json.get('code', ''): rsp_parts.append(f"code={code}")
                if msg := json.get('msg', ''): rsp_parts.append(f"msg={msg}")
                if details := json.get('details', ''): rsp_parts.append(f"details={details}")

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

