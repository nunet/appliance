# nunet_api/app/schemas.py
from dataclasses import Field
from pydantic import BaseModel
from pydantic import Field as PydField
from typing import Optional, List

__all__ = [
    "CommandResult",
    "InstallStatus",
    "DmsStatus",
    "PeerInfo",
    "ResourcesInfo",
    "SshStatus",
    "DeploymentWebItem",
    "DeploymentsWebResponse",
    "RunningItem",
    "RunningListResponse",
    "ManifestTextResponse",
    "LogsTextResponse",
    "DeployRequest",
    "DeployResponse",
    "ShutdownResponse",
    "TemplatesListItem",
    "TemplatesListResponse",
    "CopyRequest",
    "CopyResponse",
    "DownloadExamplesRequest",
    "SimpleStatusResponse",
]

class CommandResult(BaseModel):
    status: str
    message: Optional[str] = None

class InstallStatus(BaseModel):
    status: str
    version: str

class DmsStatus(BaseModel):
    dms_status: str
    dms_version: str
    dms_running: bool
    dms_context: str
    dms_did: str
    dms_peer_id: str
    dms_is_relayed: Optional[bool] = None

class PeerInfo(BaseModel):
    peer_id: str
    context: str
    did: str
    local_addrs: List[str]
    public_addrs: List[str]
    relay_addrs: List[str]
    is_relayed: bool

class ResourcesInfo(BaseModel):
    onboarding_status: str
    free_resources: str
    allocated_resources: str
    onboarded_resources: str

class SshStatus(BaseModel):
    running: bool
    authorized_keys: int

class DeploymentWebItem(BaseModel):
    id: str
    status: str
    type: str
    timestamp: str
    ensemble_file: str

class DeploymentsWebResponse(BaseModel):
    status: str
    deployments: List[DeploymentWebItem]
    count: int

class RunningItem(BaseModel):
    id: str
    status: str
    active: bool
    type: str
    timestamp: str
    file_name: str

class RunningListResponse(BaseModel):
    status: str
    message: str
    count: int
    items: List[RunningItem]

class ManifestTextResponse(BaseModel):
    status: str
    message: str

class LogsTextResponse(BaseModel):
    status: str
    message: str

class DeployRequest(BaseModel):
    file_path: str
    timeout: Optional[int] = 60

class DeployResponse(BaseModel):
    status: str
    message: str
    deployment_id: Optional[str] = None

class ShutdownResponse(BaseModel):
    status: str
    message: str

class TemplatesListItem(BaseModel):
    index: int
    name: str
    path: str
    relative_path: str

class TemplatesListResponse(BaseModel):
    items: List[TemplatesListItem]

class CopyRequest(BaseModel):
    source: str
    dest: str

class CopyResponse(BaseModel):
    status: str
    message: str

class DownloadExamplesRequest(BaseModel):
    repo: Optional[str] = None
    branch: Optional[str] = None
    source_dir: Optional[str] = None
    target_dir: Optional[str] = None

class SimpleStatusResponse(BaseModel):
    status: str
    message: str


class ConnectedPeer(BaseModel):
    peer_id: str
    did: Optional[str] = None
    context: Optional[str] = None
    local_addrs: List[str] = PydField(default_factory=list)
    public_addrs: List[str] = PydField(default_factory=list)
    relay_addrs: List[str] = PydField(default_factory=list)
    is_relayed: Optional[bool] = None

class ConnectedPeers(BaseModel):
    count: int
    peers: List[ConnectedPeer]
    # if we can't confidently parse, raw holds the original text
    raw: Optional[str] = None

class FullStatusCombined(BaseModel):
    resources: ResourcesInfo
    dms: DmsStatus
    summary_text: str
