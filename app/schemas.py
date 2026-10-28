"""API request contracts shared by route handlers."""
from pydantic import BaseModel, Field
from typing import Annotated, Literal
from typing_extensions import TypedDict


Question = Annotated[str, Field(max_length=16000)]
DocumentId = Annotated[str, Field(max_length=128)]


class HistoryMessage(TypedDict):
    role: Literal['user', 'assistant']
    content: Annotated[str, Field(max_length=32000)]


class QueryRequest(BaseModel):
    query: Question
    doc_id: DocumentId
    include_baseline: bool = False


class ChatRequest(BaseModel):
    query: Question
    doc_id: DocumentId
    previous_question: Question = ""
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)


class CustomCheckItem(BaseModel):
    id: str
    title: str
    query: Question
    category: str = "Custom Compliance"
    criticality: str = "HIGH"
    required_terms: list[str] = Field(default_factory=list)
    disqualifying_phrases: list[str] = Field(default_factory=list)
    standard_clause: str = ""
    action_required: str = ""
    rationale: str = ""


class ComplianceAuditRequest(BaseModel):
    doc_id: DocumentId
    framework: str = "sla"
    custom_checks: list[CustomCheckItem] = Field(default_factory=list, max_length=100)


class ExportReportRequest(BaseModel):
    query: str
    answer: str
    sources: list = Field(default_factory=list)
    classification: dict = Field(default_factory=dict)
    evaluation: dict = Field(default_factory=dict)
    baseline: str = ""
    format: str = "markdown"


