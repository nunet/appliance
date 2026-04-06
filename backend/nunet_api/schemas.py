# nunet_api/app/schemas.py
from dataclasses import Field
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field as PydField
from typing import Any, Dict, Literal, Optional, List

__all__ = [
    "CommandResult",
    "InstallStatus",
    "DmsStatus",
    "PeerInfo",
    "ResourcesInfo",
    "SshStatus",
    "EnvironmentStatus",
    "DeploymentWebItem",
    "DeploymentsWebResponse",
    "RunningItem",
    "RunningListResponse",
    "ManifestTextResponse",
    "LogsTextResponse",
    "DmsLogsResponse",
    "DeployRequest",
    "DeployResponse",
    "ShutdownResponse",
    "TemplatesListItem",
    "TemplatesListResponse",
    "CopyRequest",
    "CopyResponse",
    "DownloadExamplesRequest",
    "SimpleStatusResponse",
    "FilesystemEntry",
    "FilesystemListResponse",
    "FilesystemUploadItem",
    "FilesystemUploadResponse",
    "FilesystemOperationItem",
    "FilesystemOperationResponse",
    "FilesystemCopyRequest",
    "FilesystemMoveRequest",
    "FilesystemDeleteRequest",
    "FilesystemCreateFolderRequest",
    "TokenConfig",
    "CardanoTokenConfig",
    "PaymentsConfig",
    "PayableItem",
    "PayablesResponse",
    "PaymentReportIn",
    "PaymentReportOut",
    "CardanoBuildRequest",
    "CardanoBuildResponse",
    "CardanoSubmitRequest",
    "CardanoSubmitResponse",
    "PaymentQuoteGetRequest",
    "PaymentQuoteGetResponse",
    "PaymentQuoteValidateRequest",
    "PaymentQuoteValidateResponse",
    "PaymentQuoteCancelRequest",
    "PaymentQuoteCancelResponse",
    "DmsTransaction",
    "DmsTransactionsList",
    "FormFieldOption", "FormField", "FormSchema",
    "SchemaFieldOverride", "SchemaHints",
    "UploadNeedsInputDetail", "UploadConfirmOverwriteDetail",
    "UploadTemplateResponse",
    "ContractState",
    "ContractPaymentType",
    "ContractBlockchain",
    "ContractMetadata",
    "ContractListResponse",
    "ContractCreateRequest",
    "ContractApproveRequest",
    "ContractTerminateRequest",
    "ContractActionResponse",
    "ContractStateResponse",
    "ContractTemplateSummary",
    "ContractTemplateDetail",
    "ContractTemplateListResponse",
    "ApplianceUptime",
    "TelemetryPluginConfig",
    "TelemetryPluginConfigUpdate",
    "TelemetryPluginStatus",
]

class TokenConfig(BaseModel):
    chain_id: int
    token_address: str
    token_symbol: str = "NTX"
    token_decimals: int = 6
    explorer_base_url: Optional[str] = None
    network_name: Optional[str] = None


class CardanoTokenConfig(BaseModel):
    chain_id: int
    token_address: str
    token_symbol: str = "NTX"
    token_decimals: int = 0
    explorer_base_url: Optional[str] = None
    network_name: Optional[str] = None
    policy_id: str
    asset_name_hex: str
    asset_name: str
    asset_name_encoded: Optional[str] = None
    asset_id: str


class PaymentsConfig(BaseModel):
    ethereum: TokenConfig
    cardano: CardanoTokenConfig

class PayableItem(BaseModel):
    payment_id: str
    toAddress: str
    amount: str
    status: str
    payment_provider: Optional[str] = None

class PayablesResponse(BaseModel):
    items: List[PayableItem]
    count: int

class PaymentReportIn(BaseModel):
    tx_hash: str
    to_address: str
    amount: str
    payment_provider: str  # maps to DMS unique_id
    blockchain: str = "ETHEREUM"
    quote_id: Optional[str] = None

class PaymentReportOut(BaseModel):
    tx_hash: str
    to_address: str
    amount: str
    payment_provider: str
    blockchain: str
    quote_id: Optional[str] = None


class CardanoBuildRequest(BaseModel):
    from_address: str
    to_address: str
    amount: str
    payment_provider: str
    change_address: Optional[str] = None


class CardanoBuildResponse(BaseModel):
    tx_cbor: str
    tx_body_cbor: str
    tx_hash: str
    fee_lovelace: str
    network: str


class CardanoSubmitRequest(BaseModel):
    tx_body_cbor: str
    witness_set_cbor: str
    payment_provider: str
    to_address: str
    amount: str
    quote_id: Optional[str] = None


class CardanoSubmitResponse(PaymentReportOut):
    fee_lovelace: Optional[str] = None


class PaymentQuoteGetRequest(BaseModel):
    unique_id: str
    dest: str = PydField(min_length=1)


class PaymentQuoteGetResponse(BaseModel):
    quote_id: str
    original_amount: str
    converted_amount: str
    pricing_currency: str
    payment_currency: str
    exchange_rate: str
    expires_at: datetime


class PaymentQuoteValidateRequest(BaseModel):
    quote_id: str
    dest: str = PydField(min_length=1)


class PaymentQuoteValidateResponse(BaseModel):
    valid: bool
    quote_id: Optional[str] = None
    original_amount: Optional[str] = None
    converted_amount: Optional[str] = None
    pricing_currency: Optional[str] = None
    payment_currency: Optional[str] = None
    exchange_rate: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class PaymentQuoteCancelRequest(BaseModel):
    quote_id: str
    dest: str = PydField(min_length=1)


class PaymentQuoteCancelResponse(BaseModel):
    status: str = "success"

class DmsTransaction(BaseModel):
    unique_id: str
    payment_validator_did: str
    contract_did: str
    to_address: str
    from_address: Optional[str] = None
    amount: str
    status: str
    tx_hash: str
    metadata: Optional[Dict[str, Any]] = None

class DmsTransactionsList(BaseModel):
    transactions: List[DmsTransaction]
    count: int



class CommandResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["success", "error", "warning"]
    message: str = ""

    # let API callers see process output
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    returncode: Optional[int] = None

    # optional scratch slot
    raw: Optional[Dict[str, Any]] = None

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


class ContractState(str, Enum):
    UNKNOWN = "UNKNOWN"
    DRAFT = "DRAFT"
    ACCEPTED = "ACCEPTED"
    APPROVED = "APPROVED"
    SIGNED = "SIGNED"
    COMPLETED = "COMPLETED"
    SETTLED = "SETTLED"
    TERMINATED = "TERMINATED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @classmethod
    def _missing_(cls, value: object) -> "ContractState":
        if isinstance(value, str):
            normalized = value.upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return cls.UNKNOWN


class ContractPaymentType(str, Enum):
    UNKNOWN = "unknown"
    BLOCKCHAIN = "blockchain"
    FIAT = "fiat"

    @classmethod
    def _missing_(cls, value: object) -> "ContractPaymentType":
        if isinstance(value, str):
            normalized = value.lower()
            for member in cls:
                if member.value == normalized:
                    return member
        return cls.UNKNOWN


class ContractBlockchain(str, Enum):
    UNKNOWN = "UNKNOWN"
    ETHEREUM = "ETHEREUM"
    POLYGON = "POLYGON"
    BSC = "BSC"
    CARDANO = "CARDANO"

    @classmethod
    def _missing_(cls, value: object) -> "ContractBlockchain":
        if isinstance(value, str):
            normalized = value.upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return cls.UNKNOWN


class ContractDIDRef(BaseModel):
    uri: str


class ContractResourceCPU(BaseModel):
    cores: Optional[int] = None
    clock_speed: Optional[int] = None


class ContractResourceMemory(BaseModel):
    size: Optional[int] = None


class ContractResourceDisk(BaseModel):
    size: Optional[int] = None


class ContractResourceConfiguration(BaseModel):
    cpu: Optional[ContractResourceCPU] = None
    ram: Optional[ContractResourceMemory] = None
    disk: Optional[ContractResourceDisk] = None

    model_config = ConfigDict(extra="allow")


class ContractTerminationOption(BaseModel):
    allowed: Optional[bool] = None
    notice_period: Optional[int] = None


class ContractPenalty(BaseModel):
    condition: Optional[str] = None
    penalty: Optional[float] = None


class ContractParticipants(BaseModel):
    provider: Optional[ContractDIDRef] = None
    requestor: Optional[ContractDIDRef] = None


class ContractPaymentDetails(BaseModel):
    payment_type: ContractPaymentType = ContractPaymentType.UNKNOWN
    requester_addr: Optional[str] = None
    provider_addr: Optional[str] = None
    currency: Optional[str] = None
    pricing_currency: Optional[str] = None
    fees_per_allocation: Optional[str] = None
    timestamp: Optional[datetime] = None
    blockchain: Optional[ContractBlockchain] = None

    model_config = ConfigDict(extra="allow")


class ContractDuration(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ContractMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    contract_did: str
    current_state: ContractState = ContractState.UNKNOWN
    list_view: Optional[str] = None
    solution_enabler_did: Optional[ContractDIDRef] = None
    payment_validator_did: Optional[ContractDIDRef] = None
    resource_configuration: Optional[ContractResourceConfiguration] = None
    termination_option: Optional[ContractTerminationOption] = None
    penalties: List[ContractPenalty] = PydField(default_factory=list)
    duration: Optional[ContractDuration] = None
    participants: Optional[ContractParticipants] = None
    payment_details: Optional[ContractPaymentDetails] = None
    paid: Optional[bool] = None
    settled: Optional[bool] = None
    signatures: Optional[Any] = None
    verification: Optional[Dict[str, Any]] = None
    contract_proof: Optional[Any] = None
    contract_terms: Optional[str] = None
    termination_started: Optional[datetime] = None
    transitions: List[Dict[str, Any]] = PydField(default_factory=list)


class ContractListResponse(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None
    contracts: List[ContractMetadata] = PydField(default_factory=list)
    filter: Optional[str] = None
    total_count: Optional[int] = None
    filtered_count: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    returncode: Optional[int] = None
    command: Optional[str] = None


class ContractStateResponse(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None
    contract: Optional[ContractMetadata] = None
    raw: Optional[Dict[str, Any]] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    returncode: Optional[int] = None
    command: Optional[str] = None


class ContractCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: Dict[str, Any]
    template_id: Optional[str] = None
    extra_args: Optional[List[str]] = None


class ContractApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_did: str
    extra_args: Optional[List[str]] = None


class ContractTerminateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_did: str
    contract_host_did: Optional[str] = None
    extra_args: Optional[List[str]] = None


class ContractActionResponse(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None
    contract_did: Optional[str] = None
    contract_file: Optional[str] = None
    template_id: Optional[str] = None
    source: Optional[Literal["local", "remote"]] = None
    contract_host_did: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    returncode: Optional[int] = None
    command: Optional[str] = None


class ContractTemplateSummary(BaseModel):
    template_id: str
    name: str
    description: Optional[str] = None
    source: Literal["local", "remote"]
    origin: Optional[str] = None
    organization_did: Optional[str] = None
    organizations: List[str] = PydField(default_factory=list)
    tags: List[str] = PydField(default_factory=list)
    categories: List[str] = PydField(default_factory=list)
    default_destination: Optional[str] = None


class ContractTemplateDetail(ContractTemplateSummary):
    contract: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class ContractTemplateListResponse(BaseModel):
    status: Literal["success", "error"]
    templates: List[ContractTemplateSummary] = PydField(default_factory=list)
    message: Optional[str] = None

class ApplianceUptime(BaseModel):
    uptime: str


class TelemetryPluginConfig(BaseModel):
    enabled: bool = False
    remote_enabled: bool = False
    local_enabled: bool = False
    dcgm_exporter_enabled: bool = False
    grafana_enabled: bool = False
    nvidia_gpu_available: bool = False
    gateway_url: str = "https://telemetry.orgs.nunet.network"
    token_set: bool = False
    token_last8: Optional[str] = None
    generated_config_path: str = "/home/ubuntu/nunet/appliance/alloy/config.generated.alloy"
    local_grafana_running: bool = False
    cadvisor_running: bool = False
    grafana_url: str = "/sys/plugins/telemetry-exporter/grafana/"


class TelemetryPluginConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    remote_enabled: Optional[bool] = None
    local_enabled: Optional[bool] = None
    dcgm_exporter_enabled: Optional[bool] = None
    grafana_enabled: Optional[bool] = None
    gateway_url: Optional[str] = None
    telemetry_token: Optional[str] = None  # Empty string clears token
    generated_config_path: Optional[str] = None


class TelemetryPluginStatus(BaseModel):
    plugin_id: str = "telemetry-exporter"
    installed_version: Optional[str] = None
    updated_at: Optional[str] = None
    alloy_installed: Optional[bool] = None
    alloy_running: Optional[bool] = None
    local_mimir_running: Optional[bool] = None
    dcgm_exporter_running: Optional[bool] = None
    local_grafana_running: Optional[bool] = None
    cadvisor_running: Optional[bool] = None
    grafana_enabled: Optional[bool] = None
    grafana_url: Optional[str] = None
    nvidia_gpu_available: Optional[bool] = None
    enabled: Optional[bool] = None
    token_set: Optional[bool] = None
    raw_status: Optional[Dict[str, Any]] = None


class TelemetryLocalMetricPoint(BaseModel):
    ts: int
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_utilization_percent: Optional[float] = None
    disk_read_bytes_per_sec: Optional[float] = None
    disk_write_bytes_per_sec: Optional[float] = None
    network_rx_bytes_per_sec: Optional[float] = None
    network_tx_bytes_per_sec: Optional[float] = None
    gpu_utilization_percent: Optional[float] = None
    gpu_temp_celsius: Optional[float] = None
    gpu_vram_used_mib: Optional[float] = None


class TelemetryLocalMetricsResponse(BaseModel):
    available: bool = False
    reason: Optional[str] = None
    range_minutes: int = 60
    step_seconds: int = 30
    points: List[TelemetryLocalMetricPoint] = PydField(default_factory=list)


class SshStatus(BaseModel):
    running: bool
    authorized_keys: int


class EnvironmentUpdateChannelStatus(BaseModel):
    channel: str
    resolved_channel: str
    fell_back: bool


class EnvironmentUpdateStatus(BaseModel):
    appliance: EnvironmentUpdateChannelStatus
    dms: EnvironmentUpdateChannelStatus


class EnvironmentEthereumStatus(BaseModel):
    chain_id: int
    token_address: str
    token_symbol: str
    token_decimals: int
    explorer_base_url: Optional[str] = None
    network_name: Optional[str] = None


class EnvironmentStatus(BaseModel):
    environment: Literal["production", "staging"]
    updates: EnvironmentUpdateStatus
    ethereum: EnvironmentEthereumStatus

class DeploymentWebItem(BaseModel):
    id: str
    status: str
    type: str
    timestamp: str
    ensemble_file: str
    ensemble_file_name: Optional[str] = None
    ensemble_file_path: Optional[str] = None
    ensemble_file_relative: Optional[str] = None
    ensemble_file_exists: Optional[bool] = None
    deployment_url: Optional[str] = None
    allocations: Optional[List[str]] = None

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
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    dms: Optional[str] = None
    allocation: Optional["AllocationLogs"] = None
    dms_logs: Optional["DmsLogBundle"] = None

class DeploymentFileResponse(BaseModel):
    status: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_relative_path: Optional[str] = None
    content: Optional[str] = None
    exists: Optional[bool] = None
    message: Optional[str] = None
    candidates: Optional[List[str]] = None

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
    category: str

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


class FilesystemEntry(BaseModel):
    name: str
    path: str
    relative_path: str
    is_dir: bool
    is_file: bool
    is_symlink: bool
    size: Optional[int] = None
    modified_at: Optional[str] = None


class FilesystemListResponse(BaseModel):
    root: str
    path: str
    relative_path: str
    parent: Optional[str] = None
    items: List[FilesystemEntry]


class FilesystemUploadItem(BaseModel):
    name: str
    path: str
    relative_path: str
    size: Optional[int] = None
    modified_at: Optional[str] = None
    overwritten: bool = False


class FilesystemUploadResponse(BaseModel):
    status: str
    message: str
    items: List[FilesystemUploadItem]
    errors: Optional[List[str]] = None


class FilesystemOperationItem(BaseModel):
    source: str
    destination: Optional[str] = None
    status: str
    message: Optional[str] = None


class FilesystemOperationResponse(BaseModel):
    status: str
    message: str
    items: List[FilesystemOperationItem]


class FilesystemCopyRequest(BaseModel):
    sources: List[str]
    destination: str
    overwrite: bool = False


class FilesystemMoveRequest(BaseModel):
    sources: List[str]
    destination: str
    overwrite: bool = False


class FilesystemDeleteRequest(BaseModel):
    paths: List[str]
    recursive: bool = False


class FilesystemCreateFolderRequest(BaseModel):
    path: str
    parents: bool = True
    exist_ok: bool = False


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


class FileLog(BaseModel):
    path: str
    exists: bool
    readable: bool
    size_bytes: Optional[int] = None
    mtime_iso: Optional[str] = None  # ISO string
    tail_lines: Optional[int] = None
    content: Optional[str] = None
    error: Optional[str] = None

class DmsLogBundle(BaseModel):
    source: Literal["journalctl", "file", "nunet-logs"] = "journalctl"
    lines: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None

class DmsLogsResponse(BaseModel):
    status: Literal["success", "error", "warning"] = "success"
    message: Optional[str] = None
    dms: Optional[str] = None
    dms_logs: Optional[DmsLogBundle] = None

class AllocationLogs(BaseModel):
    dir: Optional[str] = None
    stdout: FileLog
    stderr: FileLog

class StructuredLogs(BaseModel):
    status: Literal["success", "error", "warning"]
    message: str
    allocation: Optional[AllocationLogs] = None
    dms_logs: Optional[DmsLogBundle] = None


LogsTextResponse.model_rebuild()
StructuredLogs.model_rebuild()


class FormFieldOption(BaseModel):
    value: Any
    label: str

class FormField(BaseModel):
    label: str
    type: Literal["text", "number", "select", "boolean"] = "text"
    options: Optional[List[FormFieldOption]] = None
    default: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    required: Optional[bool] = True
    placeholder: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    pattern: Optional[str] = None

class FormSchema(BaseModel):
    name: str
    description: Optional[str] = None
    fields: Dict[str, FormField] = PydField(default_factory=dict)

class SchemaFieldOverride(BaseModel):
    type: Optional[Literal["text", "number", "select", "boolean"]] = None
    options: Optional[List[FormFieldOption]] = None
    default: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    required: Optional[bool] = None
    placeholder: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    pattern: Optional[str] = None

class SchemaHints(BaseModel):
    """
    Optional hints to improve auto-generated schema.
    - name/description shape the form meta
    - field_overrides lets callers set types, ranges, select options, etc.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    field_overrides: Dict[str, SchemaFieldOverride] = PydField(default_factory=dict)

# --- Convenience error detail shapes (used in HTTPException.detail) ---

class UploadNeedsInputDetail(BaseModel):
    status: Literal["needs_input"] = "needs_input"
    message: str
    prompts: List[Dict[str, Any]]  # e.g., [{"field":"bird_color","required_keys":["options"],"reason":"select_missing_options","examples":[...]}]

class UploadConfirmOverwriteDetail(BaseModel):
    status: Literal["confirm_overwrite"] = "confirm_overwrite"
    message: str
    existing_paths: Dict[str, Optional[str]]  # {"yaml": "...", "json": "..."}

class UploadTemplateResponse(BaseModel):
    status: Literal["success", "error"]
    yaml_path: Optional[str] = None
    json_path: Optional[str] = None
    name: Optional[str] = None
    size: Optional[int] = None
    modified_at: Optional[str] = None
    message: Optional[str] = None
