import difflib
import re
from typing import List, Dict, Any, Optional
from app.retriever import HybridRetriever, tokenize_words, STOP_WORDS
from app.evaluator import evaluate_relevance

DEFAULT_COMPLIANCE_CHECKS = [
    {
        "id": "SLA-01",
        "category": "Service Level Agreement",
        "title": "Minimum Service Uptime Guarantee",
        "query": "What is the guaranteed service availability or uptime percentage?",
        "criticality": "HIGH",
        "required_terms": ["uptime", "availability", "99", "sla", "guarantee", "guarantees"],
        "disqualifying_phrases": ["no uptime guarantee", "no availability guarantee", "best effort only", "as-is without"]
    },
    {
        "id": "PEN-02",
        "category": "Commercial Risk",
        "title": "Breach Penalty & Invoice Credit Clause",
        "query": "What penalty credit or invoice discount applies if availability drops?",
        "criticality": "HIGH",
        "required_terms": ["penalty", "credit", "invoice", "discount", "billing"],
        "disqualifying_phrases": ["no penalty", "no billing credit", "waives all credits", "non-refundable"]
    },
    {
        "id": "SEC-03",
        "category": "Data Security & Access",
        "title": "Zero-Trust & Hardware-Enforced MFA",
        "query": "What are the rules for credential storage, MFA, and access control?",
        "criticality": "CRITICAL",
        "required_terms": ["mfa", "sso", "credentials", "authentication", "access"],
        "disqualifying_phrases": ["without mfa", "mfa is optional", "may store credentials on local"]
    },
    {
        "id": "INC-04",
        "category": "Operational Resilience",
        "title": "Incident Escalation Notification Timeline",
        "query": "What are the mandatory logging and notification steps for security alerts?",
        "criticality": "HIGH",
        "required_terms": ["incident", "escalation", "minutes", "hour", "logged", "notice", "alert"],
        "disqualifying_phrases": ["no notification required", "at vendor discretion"]
    },
    {
        "id": "FIN-05",
        "category": "Financial Controls",
        "title": "Dual Executive Sign-off for Wire Transfers",
        "query": "What is the dollar threshold requiring dual authorization for wire disbursements?",
        "criticality": "MEDIUM",
        "required_terms": ["wire", "dual", "authorization", "disbursements", "sign-off", "cfo"],
        "disqualifying_phrases": ["single signature", "no dual authorization", "solely by virtual assistant"]
    },
    {
        "id": "BCP-06",
        "category": "Business Continuity",
        "title": "Disaster Recovery RTO & Off-site Failover",
        "query": "What is the disaster recovery failover timeline and recovery time objective RTO?",
        "criticality": "HIGH",
        "required_terms": ["disaster", "recovery", "rto", "failover", "standby"],
        "disqualifying_phrases": ["no disaster recovery", "no failover"]
    },
    {
        "id": "ESG-07",
        "category": "Regulatory & ESG",
        "title": "Carbon Emission Offsets & Environmental Quota",
        "query": "What are the greenhouse gas carbon emission offset metrics and environmental reporting targets?",
        "criticality": "MEDIUM",
        "required_terms": ["carbon", "emission", "emissions", "ghg", "environmental", "offset", "offsets"],
        "disqualifying_phrases": ["exempt from environmental", "no carbon reporting"]
    }
]

COMPLIANCE_REMEDIATION_PLAYBOOK: Dict[str, Dict[str, str]] = {
    "SLA-01": {
        "standard_clause": "2.1 Minimum Service Uptime: The Service Provider guarantees a monthly service availability of not less than 99.9% during client business hours, excluding scheduled maintenance.",
        "rationale": "Defines an unambiguous mathematical threshold for availability breach enforcement.",
        "action_required": "Insert formal uptime availability baseline into the Service Level Agreement section."
    },
    "PEN-02": {
        "standard_clause": "2.2 Penalty Credit: In the event monthly availability drops below 99.5%, client shall be entitled to an immediate 15% billing credit applied to the subsequent invoice cycle.",
        "rationale": "Enforces commercial accountability and eliminates vendor breach impunity.",
        "action_required": "Add contractual billing discount trigger upon SLA failure."
    },
    "SEC-03": {
        "standard_clause": "3.1 Zero-Trust & Hardware MFA: Remote contractors must access enterprise systems exclusively via hardware-enforced FIDO2/MFA and enterprise SSO. Storing credentials on personal local drives is strictly prohibited.",
        "rationale": "Satisfies ISO 27001 / SOC 2 access control and credential leakage requirements.",
        "action_required": "Mandate hardware tokens and ban local credential persistence."
    },
    "INC-04": {
        "standard_clause": "3.2 Incident Escalation: Any suspected unauthorized data access must be formally logged within 15 minutes of occurrence and written notice served to the Client Security Officer within 1 hour.",
        "rationale": "Establishes tight breach containment and regulatory disclosure windows.",
        "action_required": "Bind vendor to 15-minute logging and 1-hour executive notification."
    },
    "FIN-05": {
        "standard_clause": "4.1 Dual Wire Authorization: All financial disbursements or wire transactions exceeding $50,000 USD require dual written authorization from the Chief Financial Officer (CFO) and Managing Director.",
        "rationale": "Prevents business email compromise (BEC) fraud and unauthorized treasury transfers.",
        "action_required": "Establish dual executive signature barrier on high-value wires."
    },
    "BCP-06": {
        "standard_clause": "5.1 Business Continuity & RTO: In the event of primary infrastructure failure, failover to secondary hot-standby systems must achieve a Recovery Time Objective (RTO) of under 2 hours.",
        "rationale": "Guarantees business continuity and caps catastrophic disaster downtime.",
        "action_required": "Incorporate explicit RTO ceiling in Disaster Recovery addendum."
    },
    "ESG-07": {
        "standard_clause": "6.1 Environmental Reporting: Vendor shall submit quarterly greenhouse gas (GHG) emission assessments and maintain certified carbon offsets for all cloud compute resources.",
        "rationale": "Complies with Scope 3 supply-chain ESG emissions disclosure directives.",
        "action_required": "Attach quarterly sustainability disclosure and offset commitment."
    }
}

FRAMEWORK_GDPR = [
    {
        "id": "GDPR-01",
        "category": "Data Governance",
        "title": "Data Protection Officer & Privacy Representative",
        "query": "Who is designated as the Data Protection Officer DPO or privacy contact point?",
        "criticality": "HIGH",
        "required_terms": ["dpo", "officer", "protection", "privacy", "contact", "representative"],
        "disqualifying_phrases": ["no dpo", "no privacy contact", "waives privacy rights"]
    },
    {
        "id": "GDPR-02",
        "category": "Breach Management",
        "title": "72-Hour Breach Notification to Supervisory Authority",
        "query": "What is the mandatory 72-hour notification timeline for personal data breaches?",
        "criticality": "CRITICAL",
        "required_terms": ["breach", "72", "hours", "notification", "authority", "supervisory", "incident"],
        "disqualifying_phrases": ["no breach notice", "unlimited time to notify", "at vendor discretion"]
    },
    {
        "id": "GDPR-03",
        "category": "Data Subject Rights",
        "title": "Data Subject Erasure (Right to be Forgotten)",
        "query": "What are the procedures for personal data deletion and erasure upon request?",
        "criticality": "HIGH",
        "required_terms": ["erasure", "deletion", "delete", "forgotten", "erased", "subject"],
        "disqualifying_phrases": ["no right to erasure", "data will never be deleted", "non-deletable"]
    },
    {
        "id": "GDPR-04",
        "category": "International Transfers",
        "title": "Standard Contractual Clauses (SCC) for Cross-Border Transfers",
        "query": "What cross-border transfer safeguards or Standard Contractual Clauses SCCs apply?",
        "criticality": "HIGH",
        "required_terms": ["cross-border", "transfer", "transfers", "scc", "clauses", "safeguards", "adequacy"],
        "disqualifying_phrases": ["unrestricted transfer", "no transfer safeguards"]
    },
    {
        "id": "GDPR-05",
        "category": "Consent & Choice",
        "title": "Unconditional Consent Withdrawal & Opt-Out",
        "query": "How can individuals withdraw consent or opt out from data processing?",
        "criticality": "MEDIUM",
        "required_terms": ["withdraw", "withdrawal", "consent", "opt-out", "revoke", "revocation"],
        "disqualifying_phrases": ["consent is irrevocable", "cannot withdraw consent"]
    },
    {
        "id": "GDPR-06",
        "category": "Storage Limitation",
        "title": "Maximum Data Retention Schedule & Automated Purge",
        "query": "What is the maximum data retention period and criteria for purging data?",
        "criticality": "MEDIUM",
        "required_terms": ["retention", "period", "purge", "purged", "months", "years", "destroy", "anonymize"],
        "disqualifying_phrases": ["retained indefinitely", "retained forever", "no retention limit"]
    }
]

GDPR_REMEDIATION_PLAYBOOK: Dict[str, Dict[str, str]] = {
    "GDPR-01": {
        "standard_clause": "7.1 Data Protection Officer: Vendor shall formally appoint an independent Data Protection Officer (DPO) and provide direct contact details to the Client for regulatory inquiries.",
        "rationale": "Mandated under GDPR Article 37 for entities processing personal data systematically or at scale.",
        "action_required": "Designate formal DPO contact in the data processing addendum."
    },
    "GDPR-02": {
        "standard_clause": "7.2 Personal Data Breach Notification: In the event of confirmed or suspected unauthorized access to personal data, Vendor shall notify Client without undue delay and at the latest within 72 hours of becoming aware of it.",
        "rationale": "Satisfies GDPR Article 33 statutory supervisory notification timelines.",
        "action_required": "Insert mandatory 72-hour maximum notice threshold for personal data incidents."
    },
    "GDPR-03": {
        "standard_clause": "7.3 Right to Erasure: Vendor shall execute verified data subject deletion or erasure requests within 30 calendar days across primary and backup data stores.",
        "rationale": "Complies with GDPR Article 17 Right to Erasure ('Right to be Forgotten').",
        "action_required": "Add 30-day erasure execution SLA for data subject requests."
    },
    "GDPR-04": {
        "standard_clause": "7.4 International Data Transfers: Transfers of personal data outside the European Economic Area (EEA) shall be governed exclusively by the European Commission Standard Contractual Clauses (SCCs).",
        "rationale": "Ensures legal transfer validity under GDPR Chapter V (Articles 44-50).",
        "action_required": "Execute Standard Contractual Clauses (SCCs) module for cross-border flows."
    },
    "GDPR-05": {
        "standard_clause": "7.5 Consent Revocation: Data subjects retain the right to withdraw consent at any time without detriment, using automated opt-out mechanisms provided by the service.",
        "rationale": "Enforces GDPR Article 7(3) requirement that consent withdrawal be as easy as giving consent.",
        "action_required": "Incorporate explicit self-service consent revocation terms."
    },
    "GDPR-06": {
        "standard_clause": "7.6 Retention & Disposal: Personal data shall be retained only as long as necessary for the specified processing purpose, not exceeding 12 months post contract termination, followed by cryptographically secure deletion.",
        "rationale": "Satisfies GDPR Article 5(1)(e) Storage Limitation principle.",
        "action_required": "Cap retention window at 12 months post-termination with automated purge commitment."
    }
}

FRAMEWORK_FINANCIAL = [
    {
        "id": "FIN-01",
        "category": "Disbursements",
        "title": "Dual Executive Sign-Off for Disbursements",
        "query": "What is the dollar threshold requiring dual authorization for wire disbursements?",
        "criticality": "HIGH",
        "required_terms": ["wire", "dual", "authorization", "disbursements", "sign-off", "threshold", "cfo"],
        "disqualifying_phrases": ["single signature", "no dual authorization", "solely by virtual assistant"]
    },
    {
        "id": "FIN-02",
        "category": "Internal Controls",
        "title": "Segregation of Financial & Accounting Duties",
        "query": "How are purchasing, invoice approval, payment release, and reconciliation duties segregated?",
        "criticality": "HIGH",
        "required_terms": ["segregation", "duties", "purchasing", "approval", "reconciliation", "accounting"],
        "disqualifying_phrases": ["single individual may approve and release", "no segregation"]
    },
    {
        "id": "FIN-03",
        "category": "Auditability",
        "title": "Immutable Transaction Audit Logging & Ledger",
        "query": "How are transaction logs and ledger entries stored to prevent unauthorized modification or deletion?",
        "criticality": "CRITICAL",
        "required_terms": ["audit", "log", "logs", "ledger", "immutable", "tamper", "append-only"],
        "disqualifying_phrases": ["logs may be deleted", "no audit trail", "no ledger logging"]
    },
    {
        "id": "FIN-04",
        "category": "Third-Party Oversight",
        "title": "Independent External Audit Rights",
        "query": "What rights exist for independent certified public accountants to audit financial records?",
        "criticality": "HIGH",
        "required_terms": ["independent", "auditor", "auditors", "audit", "inspection", "records", "cpa"],
        "disqualifying_phrases": ["no audit rights", "audit strictly prohibited", "vendor records exempt"]
    },
    {
        "id": "FIN-05",
        "category": "Record Keeping",
        "title": "Statutory Financial Record Retention",
        "query": "What is the mandatory retention timeline for fiscal books, tax records, and invoices?",
        "criticality": "MEDIUM",
        "required_terms": ["retention", "years", "records", "invoices", "tax", "fiscal", "books"],
        "disqualifying_phrases": ["records discarded annually", "no record retention"]
    }
]

FINANCIAL_REMEDIATION_PLAYBOOK: Dict[str, Dict[str, str]] = {
    "FIN-01": {
        "standard_clause": "4.1 Dual Wire Authorization: All financial disbursements or wire transactions exceeding $50,000 USD require dual written authorization from the Chief Financial Officer (CFO) and Managing Director.",
        "rationale": "Prevents business email compromise (BEC) fraud and unauthorized treasury transfers.",
        "action_required": "Establish dual executive signature barrier on high-value wires."
    },
    "FIN-02": {
        "standard_clause": "4.2 Segregation of Duties: No single employee may initiate, approve, and execute disbursements or reconcile bank accounts without independent secondary verification.",
        "rationale": "Core requirement under SOX Section 404 internal accounting control frameworks.",
        "action_required": "Mandate formal separation between purchase approval and disbursement release."
    },
    "FIN-03": {
        "standard_clause": "4.3 Immutable Ledger & Audit Trail: All ledger transactions, adjustments, and disbursement events must be written to write-once-read-many (WORM) audit storage with cryptographic integrity validation.",
        "rationale": "Guarantees tamper-evident transaction logs for forensic financial reviews.",
        "action_required": "Implement immutable transaction logging with cryptographic chaining."
    },
    "FIN-04": {
        "standard_clause": "4.4 External Audit Rights: Client and its certified independent auditors retain the right, upon 10 business days notice, to inspect financial books and records relevant to contract billing.",
        "rationale": "Standard governance protection against billing irregularities and cost inflation.",
        "action_required": "Insert annual audit right for independent accounting firms."
    },
    "FIN-05": {
        "standard_clause": "4.5 Statutory Record Retention: All financial invoices, bank statements, and tax reconciliations must be securely preserved for a minimum of 7 years following transaction closing.",
        "rationale": "Satisfies statutory tax authority and commercial code record retention obligations.",
        "action_required": "Enforce mandatory 7-year retention rule for all billing and ledger artifacts."
    }
}

AVAILABLE_FRAMEWORKS: Dict[str, Dict[str, Any]] = {
    "sla": {
        "name": "Cloud Vendor Service Level Agreement (SLA)",
        "description": "Standard SLA, credit penalties, MFA, incident escalation, and disaster recovery controls.",
        "checks": DEFAULT_COMPLIANCE_CHECKS,
        "playbook": COMPLIANCE_REMEDIATION_PLAYBOOK,
    },
    "gdpr": {
        "name": "GDPR / EU Data Protection Standard",
        "description": "72h breach reporting, DPO, data subject erasure, consent withdrawal, and SCC transfer safeguards.",
        "checks": FRAMEWORK_GDPR,
        "playbook": GDPR_REMEDIATION_PLAYBOOK,
    },
    "financial": {
        "name": "Corporate Financial Controls & SOX Governance",
        "description": "Dual disbursement authorization, segregation of duties, audit trails, and independent inspection.",
        "checks": FRAMEWORK_FINANCIAL,
        "playbook": FINANCIAL_REMEDIATION_PLAYBOOK,
    },
}


def verify_control_substance(excerpt: str, check: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifies that a retrieved excerpt actually addresses the compliance control substance
    rather than merely sharing superficial embedding similarity, and checks for disqualifying negations.
    """
    if not excerpt or not excerpt.strip():
        return {"substantive_pass": False, "matched_terms": [], "reason": "Empty clause excerpt."}

    excerpt_lower = excerpt.lower()
    for bad_phrase in check.get("disqualifying_phrases", []):
        if bad_phrase in excerpt_lower:
            return {
                "substantive_pass": False,
                "matched_terms": [],
                "reason": f"Clause explicitly negates control requirement ('{bad_phrase}')."
            }

    words = set(tokenize_words(excerpt_lower))
    required = check.get("required_terms", [])
    if not required and check.get("query"):
        raw_tokens = tokenize_words(check["query"])
        required = [t for t in raw_tokens if t not in STOP_WORDS and len(t) > 2]

    matched = [
        term for term in required
        if term in words or re.search(r'\b' + re.escape(term) + r'\b', excerpt_lower)
    ]

    # Require at least 2 domain control terms (or 1 if the control has <= 2 terms)
    min_required = min(2, len(required)) if required else 0
    return {
        "substantive_pass": len(matched) >= min_required,
        "matched_terms": matched,
        "reason": "Control terms verified." if len(matched) >= min_required else "Insufficient control-specific terms in excerpt."
    }


def generate_redline_diff(original_text: str, target_clause: str, control_id: str) -> str:
    """Generates a clean unified git-style diff showing the proposed remediation insertion."""
    from_lines = [f"{original_text}\n"] if original_text and original_text.strip() else []
    to_lines = [
        f"@@ -0,0 +1,2 @@ # [REMEDIATION INSERTION - {control_id}]\n",
        f"+ {target_clause}\n"
    ]
    diff = difflib.unified_diff(
        from_lines,
        to_lines,
        fromfile="Active Document (Current)",
        tofile=f"Compliance Standard ({control_id})"
    )
    return "".join(diff)


def run_compliance_audit(
    retriever: HybridRetriever,
    checks: Optional[List[Dict[str, Any]]] = None,
    playbook: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Executes an automated multi-point pre-flight compliance audit across the active document.
    Combines hybrid retrieval, CRAG relevance thresholding, and substantive control term & polarity verification.
    Supports default SLA checks or custom dynamic compliance frameworks.
    """
    active_checks = checks if checks is not None else DEFAULT_COMPLIANCE_CHECKS
    active_playbook = playbook if playbook is not None else COMPLIANCE_REMEDIATION_PLAYBOOK

    results = []
    passed_count = 0
    gaps_count = 0

    for check in active_checks:
        retrieved = retriever.retrieve(check["query"], top_k=2)
        eval_res = evaluate_relevance(retrieved, query=check["query"])
        remediation = active_playbook.get(check["id"], {})

        std_clause = (
            remediation.get("standard_clause")
            or check.get("standard_clause")
            or f"Standard compliance clause required for {check.get('title', check.get('id'))}."
        )
        action = (
            remediation.get("action_required")
            or check.get("action_required")
            or f"Incorporate mandatory {check.get('title', check.get('id'))} requirements into the document."
        )
        rationale = (
            remediation.get("rationale")
            or check.get("rationale")
            or f"Mandatory compliance control for {check.get('category', 'Compliance')}."
        )

        best_chunk = retrieved[0] if retrieved else {}
        excerpt = best_chunk.get("parent_text", best_chunk.get("child_text", "")) if best_chunk else ""
        substance = verify_control_substance(excerpt, check)

        ctrl_title = check.get("title") or check.get("control", check.get("id", "Control"))
        ctrl_cat = check.get("category", "General")
        ctrl_crit = check.get("criticality", "HIGH")

        if eval_res["status"] == "SYNTHESIZE" and substance["substantive_pass"]:
            lines = [ln.strip() for ln in excerpt.splitlines() if ln.strip()]
            clean_excerpt = lines[0] if lines else ""
            if len(clean_excerpt) < 30 and len(lines) > 1:
                clean_excerpt = f"{clean_excerpt} {lines[1]}"
            if len(clean_excerpt) > 130:
                clean_excerpt = clean_excerpt[:127] + "..."

            passed_count += 1
            results.append({
                "id": check["id"],
                "control": ctrl_title,
                "category": ctrl_cat,
                "title": ctrl_title,
                "criticality": ctrl_crit,
                "status": "PASS",
                "badge": "✅ PASS",
                "retrieval_score": eval_res["retrieval_score"],
                "matched_terms": substance["matched_terms"],
                "clause_excerpt": clean_excerpt,
                "excerpt": clean_excerpt,
                "full_clause": excerpt,
                "page": best_chunk.get("page", 1),
                "image_url": best_chunk.get("image_url", ""),
                "citation_id": best_chunk.get("citation_id", 1),
                "finding": f"Control terms found in Section/Page {best_chunk.get('page', 1)} (retrieval score {eval_res['retrieval_score']}; not a probability; matched: {', '.join(substance['matched_terms'][:4])}).",
                "remediation_clause": "Compliant with enterprise standard. No remediation required.",
                "redline_diff": None,
                "action_plan": "Verified active in document.",
                "rationale": rationale
            })
        else:
            gaps_count += 1
            redline = generate_redline_diff("", std_clause, check["id"])
            gap_msg = "Clause not present in agreement or below retrieval threshold."
            if eval_res["status"] == "SYNTHESIZE" and not substance["substantive_pass"]:
                gap_msg = substance["reason"]

            results.append({
                "id": check["id"],
                "control": ctrl_title,
                "category": ctrl_cat,
                "title": ctrl_title,
                "criticality": ctrl_crit,
                "status": "GAP",
                "badge": "❌ GAP DETECTED",
                "retrieval_score": eval_res["retrieval_score"],
                "matched_terms": substance["matched_terms"],
                "clause_excerpt": gap_msg,
                "excerpt": gap_msg,
                "full_clause": "",
                "page": None,
                "image_url": "",
                "citation_id": None,
                "finding": f"HIGH AUDIT RISK: {action}",
                "remediation_clause": std_clause,
                "redline_diff": redline,
                "action_plan": action,
                "rationale": rationale
            })

    total_checks = len(active_checks)
    score_pct = round((passed_count / total_checks) * 100, 1) if total_checks else 100.0

    if score_pct >= 80:
        verdict = "AUDIT PASSED (CONDITIONAL)"
        verdict_color = "emerald"
    elif score_pct >= 50:
        verdict = "WARNING: DEFICIENCIES DETECTED"
        verdict_color = "amber"
    else:
        verdict = "FAILED AUDIT (CRITICAL GAPS)"
        verdict_color = "red"

    return {
        "overall_score": score_pct,
        "total_checks": total_checks,
        "total_controls": total_checks,
        "passed_count": passed_count,
        "gaps_count": gaps_count,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "checklist": results,
        "remediation_count": gaps_count,
        "remediation_playbook_available": True
    }
