from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Dict, Iterable, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from modules.contract_templates import get_contract_template as fetch_contract_template, list_contract_templates
from modules.dms_manager import DMSManager
from ..schemas import (
    ContractActionResponse,
    ContractApproveRequest,
    ContractCreateRequest,
    ContractListResponse,
    ContractMetadata,
    ContractStateResponse,
    ContractTerminateRequest,
    ContractTemplateDetail,
    ContractTemplateListResponse,
    ContractTemplateSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_mgr() -> DMSManager:
    return DMSManager()


def _normalize_contract_entry(entry: Any) -> Optional[ContractMetadata]:
    if not isinstance(entry, dict):
        return None
    data = dict(entry)
    if "contract_did" not in data or not data.get("contract_did"):
        for key in ("ContractDID", "contractDid", "contract_id", "ContractID"):
            value = entry.get(key)
            if value:
                data["contract_did"] = value
                break
    if "current_state" not in data or not data.get("current_state"):
        for key in ("CurrentState", "state", "State"):
            value = entry.get(key)
            if value:
                data["current_state"] = value
                break
    if "participants" not in data and entry.get("contract_participants"):
        data["participants"] = entry["contract_participants"]
    try:
        return ContractMetadata.model_validate(data)
    except ValidationError as exc:
        logger.debug("Unable to parse contract payload %s: %s", data, exc)
        return None


def _parse_contracts(items: Iterable[Any]) -> list[ContractMetadata]:
    parsed: list[ContractMetadata] = []
    for item in items:
        normalized = _normalize_contract_entry(item)
        if normalized:
            parsed.append(normalized)
        else:
            logger.debug("Skipping contract entry due to validation issues: %s", item)
    return parsed


def _build_list_response(result: Dict[str, Any]) -> ContractListResponse:
    filtered_contracts = result.get("contracts") or []
    parsed = _parse_contracts(filtered_contracts)
    raw_payload = result.get("raw") or {"contracts": filtered_contracts}
    return ContractListResponse(
        status="success",
        message=result.get("message"),
        contracts=parsed,
        filter=result.get("filter"),
        total_count=result.get("total_count"),
        filtered_count=result.get("filtered_count"),
        raw=raw_payload,
        stdout=result.get("stdout"),
        stderr=result.get("stderr"),
        returncode=result.get("returncode"),
        command=result.get("command"),
    )


def _build_state_response(result: Dict[str, Any]) -> ContractStateResponse:
    contract_payload = result.get("contract")
    contract_model = _normalize_contract_entry(contract_payload)
    raw_payload = contract_payload if isinstance(contract_payload, dict) else None
    return ContractStateResponse(
        status="success",
        message=result.get("message"),
        contract=contract_model,
        raw=raw_payload,
        stdout=result.get("stdout"),
        stderr=result.get("stderr"),
        returncode=result.get("returncode"),
        command=result.get("command"),
    )


def _build_action_response(
    result: Dict[str, Any],
    *,
    contract_did: Optional[str] = None,
    contract_host_did: Optional[str] = None,
    template_meta: Optional[Dict[str, Any]] = None,
) -> ContractActionResponse:
    template_id = (template_meta or {}).get("template_id") or result.get("template_id")
    source = (template_meta or {}).get("source") or result.get("source")
    organisation = (template_meta or {}).get("organization_did") or result.get("organization_did")
    return ContractActionResponse(
        status="success",
        message=result.get("message"),
        contract_did=contract_did or result.get("contract_did"),
        contract_file=result.get("contract_file"),
        destination=result.get("destination"),
        template_id=template_id,
        source=source,
        organization_did=organisation,
        contract_host_did=contract_host_did or result.get("contract_host_did"),
        stdout=result.get("stdout"),
        stderr=result.get("stderr"),
        returncode=result.get("returncode"),
        command=result.get("command"),
    )


def _raise_contract_error(result: Dict[str, Any], fallback: str) -> None:
    detail = {
        "message": result.get("message") or result.get("error") or fallback,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "returncode": result.get("returncode"),
        "command": result.get("command"),
    }
    raise HTTPException(status_code=502, detail=detail)


def _template_to_summary(template: Dict[str, Any]) -> ContractTemplateSummary:
    return ContractTemplateSummary(
        template_id=template.get("template_id"),
        name=template.get("display_name") or template.get("template_id"),
        description=template.get("description"),
        source=template.get("source", "local"),
        origin=template.get("origin"),
        organization_did=template.get("organization_did"),
        organizations=template.get("organizations") or [],
        tags=template.get("tags") or [],
        categories=template.get("categories") or [],
        default_destination=template.get("default_destination")
        or (template.get("metadata") or {}).get("default_destination"),
    )


def _template_to_detail(template: Dict[str, Any]) -> ContractTemplateDetail:
    detail = _template_to_summary(template).model_dump()
    detail["contract"] = template.get("contract", {})
    if "metadata" in template:
        detail["metadata"] = template["metadata"]
    return ContractTemplateDetail(**detail)


@router.get("/templates", response_model=ContractTemplateListResponse)
def list_contract_templates_endpoint(
    org_did: Optional[str] = Query(None, description="Filter templates for a specific organization DID."),
) -> ContractTemplateListResponse:
    templates = list_contract_templates(org_did=org_did)
    summaries = [_template_to_summary(template) for template in templates]
    message = None if summaries else "No contracts yet"
    return ContractTemplateListResponse(status="success", templates=summaries, message=message)


@router.get("/templates/{template_id}", response_model=ContractTemplateDetail)
def get_contract_template_endpoint(
    template_id: str,
    org_did: Optional[str] = Query(None, description="When provided, include organization-specific templates."),
) -> ContractTemplateDetail:
    template = fetch_contract_template(template_id, org_did=org_did)
    if not template:
        raise HTTPException(status_code=404, detail={"message": f"Contract template '{template_id}' not found"})
    return _template_to_detail(template)


@router.get("/", response_model=ContractListResponse)
@router.get("", response_model=ContractListResponse, include_in_schema=False)
def list_contracts_endpoint(
    view: Literal["incoming", "active", "all"] = Query(
        "all",
        description="Filter contracts by lifecycle view.",
    ),
    mgr: DMSManager = Depends(get_mgr),
) -> ContractListResponse:
    if view == "incoming":
        result = mgr.list_incoming_contracts()
        if result.get("status") != "success":
            _raise_contract_error(result, "Failed to list incoming contracts")
        return _build_list_response(result)

    if view == "active":
        result = mgr.list_signed_contracts()
        if result.get("status") != "success":
            _raise_contract_error(result, "Failed to list active contracts")
        return _build_list_response(result)

    incoming_result = mgr.list_incoming_contracts()
    if incoming_result.get("status") != "success":
        _raise_contract_error(incoming_result, "Failed to list incoming contracts")

    active_result = mgr.list_signed_contracts()
    if active_result.get("status") != "success":
        _raise_contract_error(active_result, "Failed to list active contracts")

    combined: dict[str, Any] = {
        "contracts": [],
        "filter": "all",
        "total_count": 0,
        "filtered_count": 0,
        "raw": {
            "incoming": incoming_result.get("raw"),
            "active": active_result.get("raw"),
        },
        "stdout": "\n".join(filter(None, [incoming_result.get("stdout"), active_result.get("stdout")])),
        "stderr": "\n".join(filter(None, [incoming_result.get("stderr"), active_result.get("stderr")])),
        "returncode": incoming_result.get("returncode"),
        "command": incoming_result.get("command"),
        "message": incoming_result.get("message"),
        "status": "success",
    }

    seen: set[str] = set()
    for source in (incoming_result, active_result):
        for entry in source.get("contracts") or []:
            if not isinstance(entry, dict):
                continue
            did = entry.get("contract_did")
            if isinstance(did, str):
                if did in seen:
                    continue
                seen.add(did)
            combined["contracts"].append(entry)

    combined["total_count"] = len(combined["contracts"])
    combined["filtered_count"] = len(combined["contracts"])

    return _build_list_response(combined)


@router.get("/incoming", response_model=ContractListResponse)
def list_incoming_contracts(mgr: DMSManager = Depends(get_mgr)) -> ContractListResponse:
    result = mgr.list_incoming_contracts()
    if result.get("status") != "success":
        _raise_contract_error(result, "Failed to list incoming contracts")
    return _build_list_response(result)


@router.get("/signed", response_model=ContractListResponse)
def list_signed_contracts(mgr: DMSManager = Depends(get_mgr)) -> ContractListResponse:
    result = mgr.list_signed_contracts()
    if result.get("status") != "success":
        _raise_contract_error(result, "Failed to list signed contracts")
    return _build_list_response(result)


@router.get("/state/{contract_did}", response_model=ContractStateResponse)
def get_contract_state(
    contract_did: str,
    contract_host_did: Optional[str] = Query(
        None,
        description="When provided, use this host DID when querying DMS for the contract state.",
    ),
    mgr: DMSManager = Depends(get_mgr),
) -> ContractStateResponse:
    result = mgr.get_contract_state(contract_did, contract_host_did=contract_host_did)
    if result.get("status") != "success":
        _raise_contract_error(result, f"Failed to fetch contract state for {contract_did}")
    return _build_state_response(result)


@router.post("/create", response_model=ContractActionResponse)
def create_contract(
    request: ContractCreateRequest,
    mgr: DMSManager = Depends(get_mgr),
) -> ContractActionResponse:
    destination = request.destination.strip() if isinstance(request.destination, str) else request.destination
    template_meta: Optional[Dict[str, Any]] = None
    if request.template_id:
        template_meta = fetch_contract_template(request.template_id, org_did=request.organization_did)
        if not template_meta:
            raise HTTPException(status_code=404, detail={"message": f"Contract template '{request.template_id}' not found"})
        if not destination:
            destination = (
                template_meta.get("default_destination")
                or (template_meta.get("metadata") or {}).get("default_destination")
            )
        template_meta = dict(template_meta)
        if request.organization_did and not template_meta.get("organization_did"):
            template_meta["organization_did"] = request.organization_did
    if not destination:
        raise HTTPException(status_code=400, detail={"message": "Destination is required to create a contract"})

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(request.contract, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        contract_path = tmp.name
    try:
        result = mgr.create_contract(
            contract_path,
            dest=destination,
            extra_args=request.extra_args,
            template_id=request.template_id,
        )
    finally:
        try:
            os.unlink(contract_path)
        except OSError as exc:
            logger.debug("Failed to remove temporary contract file %s: %s", contract_path, exc)

    if result.get("status") != "success":
        _raise_contract_error(result, "Failed to create contract")

    if template_meta:
        template_meta["template_id"] = template_meta.get("template_id") or request.template_id
    return _build_action_response(result, template_meta=template_meta)


@router.post("/approve", response_model=ContractActionResponse)
def approve_contract(
    request: ContractApproveRequest,
    mgr: DMSManager = Depends(get_mgr),
) -> ContractActionResponse:
    result = mgr.approve_contract(
        request.contract_did,
        extra_args=request.extra_args,
    )
    if result.get("status") != "success":
        _raise_contract_error(result, f"Failed to approve contract {request.contract_did}")
    return _build_action_response(result, contract_did=request.contract_did)


@router.post("/terminate", response_model=ContractActionResponse)
def terminate_contract(
    request: ContractTerminateRequest,
    mgr: DMSManager = Depends(get_mgr),
) -> ContractActionResponse:
    result = mgr.terminate_contract(
        request.contract_did,
        contract_host_did=request.contract_host_did,
        extra_args=request.extra_args,
    )
    if result.get("status") != "success":
        _raise_contract_error(result, f"Failed to terminate contract {request.contract_did}")
    return _build_action_response(
        result,
        contract_did=request.contract_did,
        contract_host_did=request.contract_host_did,
    )
