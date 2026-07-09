"""Pydantic schemas: LLM extraction contracts + API request/response models."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

FeeType = Literal["lump_sum", "tm"]
UnitType = Literal["day", "month", "hour", "lump_sum", "other"] | None
LineCategory = Literal["labor", "reimbursable", "expense"]

# ---------------------------------------------------------------------------
# LLM extraction schemas (contract Exhibit B parsing)
# ---------------------------------------------------------------------------


class ContractTaskExtract(BaseModel):
    task_number: str
    cost_code: str | None = None
    description: str
    fee_type: FeeType = "tm"
    unit_type: UnitType = None
    unit_rate: float | None = None
    estimated_fee: float = 0.0
    markup_pct: float | None = None
    is_active: bool = True
    superseded_by_task_number: str | None = None
    notes: str | None = None


class ContractExtractionResult(BaseModel):
    label: str | None = None
    not_to_exceed_total: float | None = None
    default_markup_pct: float | None = None
    tasks: list[ContractTaskExtract] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM extraction schemas (invoice parsing — unsorted T&M receipts)
# ---------------------------------------------------------------------------


class InvoiceLineItemExtract(BaseModel):
    raw_task_number: str | None = None
    raw_cost_code: str | None = None
    description: str
    work_date: str | None = None  # ISO date if determinable
    person_name: str | None = None
    quantity: float | None = None
    unit_type: UnitType = None
    unit_rate: float | None = None
    amount: float = 0.0
    category: LineCategory = "labor"


class InvoiceExtractionResult(BaseModel):
    invoice_number: str | None = None
    invoice_date: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    subtotal: float | None = None
    total_amount: float | None = None
    reimbursable_amount: float | None = None
    reimbursable_markup_billed: float | None = None
    line_items: list[InvoiceLineItemExtract] = Field(default_factory=list)


class TaskCorrelationExtract(BaseModel):
    """One row already correlated to a task number on a pre-formatted billing sheet invoice."""

    raw_task_number: str | None = None
    raw_cost_code: str | None = None
    description: str
    previously_billed: float | None = None
    billed_this_period: float | None = None
    total_billed_to_date: float | None = None
    estimated_fee: float | None = None


class InspectionDatesExtract(BaseModel):
    period_start: str | None = None
    period_end: str | None = None
    inspection_dates: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API response schemas
# ---------------------------------------------------------------------------


class ContractTaskResponse(BaseModel):
    id: int
    task_number: str
    cost_code: str | None
    description: str
    fee_type: str
    unit_type: str | None
    unit_rate: float | None
    estimated_fee: float
    markup_pct: float | None
    is_active: bool
    superseded_by_task_number: str | None
    notes: str | None

    model_config = {"from_attributes": True}


class ContractResponse(BaseModel):
    id: int
    project_id: int
    file_name: str
    label: str | None
    not_to_exceed_total: float | None
    default_markup_pct: float | None
    status: str
    uploaded_at: datetime
    tasks: list[ContractTaskResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class InvoiceLineItemResponse(BaseModel):
    id: int
    contract_task_id: int | None
    raw_task_number: str | None
    raw_cost_code: str | None
    description: str
    work_date: date | None
    person_name: str | None
    quantity: float | None
    unit_type: str | None
    unit_rate: float | None
    amount: float
    previously_billed: float | None
    billed_this_period: float | None
    total_billed_to_date: float | None
    category: str
    correlation_confidence: str | None

    model_config = {"from_attributes": True}


class ReviewFlagResponse(BaseModel):
    id: int
    contract_task_id: int | None
    rule_code: str
    severity: str
    message: str

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: int
    project_id: int
    file_name: str
    invoice_number: str | None
    invoice_date: date | None
    period_start: date | None
    period_end: date | None
    invoice_format: str
    subtotal: float | None
    total_amount: float | None
    reimbursable_amount: float | None
    reimbursable_markup_billed: float | None
    status: str
    uploaded_at: datetime
    line_items: list[InvoiceLineItemResponse] = Field(default_factory=list)
    flags: list[ReviewFlagResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: int
    name: str
    consultant_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InspectionReportSummary(BaseModel):
    id: int
    file_name: str
    period_start: date | None = None
    period_end: date | None = None
    inspection_date_count: int = 0

    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    contracts: list[ContractResponse] = Field(default_factory=list)
    invoices: list[InvoiceResponse] = Field(default_factory=list)
    inspection_reports: list[InspectionReportSummary] = Field(default_factory=list)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    consultant_name: str | None = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class TaskSummaryRow(BaseModel):
    """One row of the billing-sheet summary tab / API summary view."""

    task_number: str
    cost_code: str | None
    description: str
    fee_type: str
    estimated_fee: float
    prior_billed: float
    billed_this_period: float
    billed_to_date: float
    pct_billed: float
    remaining: float
    is_active: bool
    flag_level: str | None = None  # None | "warning" | "critical"


class BillingSummaryResponse(BaseModel):
    rows: list[TaskSummaryRow]
    contract_total: float
    total_billed_to_date: float
    total_remaining: float


class EmailDraftResponse(BaseModel):
    subject: str
    body: str
