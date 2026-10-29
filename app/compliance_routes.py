"""Compliance audit and discrepancy routes."""
import asyncio
from fastapi import APIRouter, HTTPException
from app.schemas import ComplianceAuditRequest
from app.audit_scanner import AVAILABLE_FRAMEWORKS

router = APIRouter()


@router.get("/api/discrepancies")
@router.get("/api/ast/discrepancies")
async def get_active_discrepancies(doc_id: str, use_llm: bool = False):
    from app import main
    entry = main.document_snapshot(doc_id)
    ast = entry.get("ast")
    if ast is None:
        raise HTTPException(status_code=404, detail="Document structure unavailable.")
    report = await asyncio.to_thread(main.scan_ast_for_discrepancies, ast, use_llm)
    report["filename"] = entry.get("filename", "Document")
    report["doc_id"] = doc_id
    return report


@router.get("/compliance-audit")
async def get_compliance_audit(doc_id: str, framework: str = "sla"):
    """Run compliance audit against the explicitly requested document."""
    from app import main
    entry = main.document_snapshot(doc_id)
    fw = AVAILABLE_FRAMEWORKS.get(framework.lower(), AVAILABLE_FRAMEWORKS["sla"])
    if framework.lower() == "sla":
        report = await asyncio.to_thread(main.run_compliance_audit, entry["retriever"])
    else:
        report = await asyncio.to_thread(
            main.run_compliance_audit,
            entry["retriever"],
            checks=fw["checks"],
            playbook=fw.get("playbook"),
        )
    report["filename"] = entry.get("filename", "Document")
    report["classification"] = entry.get("classification", {})
    report["doc_id"] = doc_id
    report["framework"] = framework.lower()
    report["framework_name"] = fw["name"]
    return report


@router.post("/compliance-audit")
async def post_compliance_audit(payload: ComplianceAuditRequest):
    """Run an on-demand compliance audit with optional custom checklist rules or domain frameworks."""
    from app import main
    entry = main.document_snapshot(payload.doc_id)
    fw_key = payload.framework.lower()

    if fw_key == "custom" and payload.custom_checks:
        checks = [c.model_dump() for c in payload.custom_checks]
        playbook = {
            c["id"]: {
                "standard_clause": c.get("standard_clause") or f"Standard clause for {c.get('title')}",
                "action_required": c.get("action_required") or f"Insert {c.get('title')} clause",
                "rationale": c.get("rationale") or f"Mandatory compliance control for {c.get('category')}",
            }
            for c in checks
        }
        fw_name = "Custom Checklist Audit"
        report = await asyncio.to_thread(
            main.run_compliance_audit,
            entry["retriever"],
            checks=checks,
            playbook=playbook,
        )
    elif fw_key == "sla":
        fw = AVAILABLE_FRAMEWORKS["sla"]
        fw_name = fw["name"]
        report = await asyncio.to_thread(main.run_compliance_audit, entry["retriever"])
    else:
        fw = AVAILABLE_FRAMEWORKS.get(fw_key, AVAILABLE_FRAMEWORKS["sla"])
        fw_name = fw["name"]
        report = await asyncio.to_thread(
            main.run_compliance_audit,
            entry["retriever"],
            checks=fw["checks"],
            playbook=fw.get("playbook"),
        )

    report["filename"] = entry.get("filename", "Document")
    report["classification"] = entry.get("classification", {})
    report["doc_id"] = payload.doc_id
    report["framework"] = fw_key
    report["framework_name"] = fw_name
    return report


@router.get("/api/compliance/frameworks")
def list_compliance_frameworks():
    """Returns list of pre-configured compliance frameworks and control counts."""
    return {
        framework_id: {
            "name": info["name"],
            "description": info["description"],
            "control_count": len(info["checks"]),
            "controls": [
                {"id": c["id"], "title": c["title"], "criticality": c["criticality"]}
                for c in info["checks"]
            ],
        }
        for framework_id, info in AVAILABLE_FRAMEWORKS.items()
    }
