"""SQLAlchemy ORM models."""

import json
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(20), default="email", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner")


class Project(Base):
    """One consultant engagement/contract to track over time (e.g. 'Riverside Tower — Acme Consulting')."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    consultant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    owner: Mapped["User | None"] = relationship("User", back_populates="projects")
    contracts: Mapped[list["Contract"]] = relationship(
        "Contract", back_populates="project", cascade="all, delete-orphan", order_by="Contract.uploaded_at"
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice", back_populates="project", cascade="all, delete-orphan", order_by="Invoice.period_start"
    )
    inspection_reports: Mapped[list["InspectionReport"]] = relationship(
        "InspectionReport", back_populates="project", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="project", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    not_to_exceed_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_markup_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="contracts")
    tasks: Mapped[list["ContractTask"]] = relationship(
        "ContractTask", back_populates="contract", cascade="all, delete-orphan", order_by="ContractTask.sort_order"
    )


class ContractTask(Base):
    """One row of the contract's Exhibit B / Schedule of Values."""

    __tablename__ = "contract_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_number: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    fee_type: Mapped[str] = mapped_column(String(20), default="tm", nullable=False)  # lump_sum | tm
    unit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # day | month | hour | lump_sum
    unit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    markup_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    superseded_by_task_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    contract: Mapped["Contract"] = relationship("Contract", back_populates="tasks")
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem", back_populates="contract_task"
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_format: Mapped[str] = mapped_column(String(20), default="tm_receipt", nullable=False)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    reimbursable_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    reimbursable_markup_billed: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="invoices")
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLineItem.id"
    )
    flags: Mapped[list["ReviewFlag"]] = relationship(
        "ReviewFlag", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    contract_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_tasks.id"), nullable=True, index=True
    )
    raw_task_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_cost_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    person_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    previously_billed: Mapped[float | None] = mapped_column(Float, nullable=True)
    billed_this_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_billed_to_date: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(20), default="labor", nullable=False)  # labor|reimbursable|expense
    correlation_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")
    contract_task: Mapped["ContractTask | None"] = relationship("ContractTask", back_populates="line_items")


class ReviewFlag(Base):
    __tablename__ = "review_flags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    contract_task_id: Mapped[int | None] = mapped_column(ForeignKey("contract_tasks.id"), nullable=True)
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False)  # info|warning|critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="flags")


class InspectionReport(Base):
    """Daily/monthly field report used to cross-check invoiced inspection dates."""

    __tablename__ = "inspection_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    inspection_dates_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of ISO dates
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="inspection_reports")

    @property
    def inspection_date_count(self) -> int:
        return len(json.loads(self.inspection_dates_json)) if self.inspection_dates_json else 0


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user|assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="chat_messages")
