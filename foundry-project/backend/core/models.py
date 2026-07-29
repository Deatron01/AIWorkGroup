# foundry-project/backend/core/models.py
import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class JobModel(Base):
    """Tracks high-level software factory projects as distinct Jobs."""
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    project_name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    current_status = Column(String, default="Pending") # Pending, Architecture, Implementation, Finished, Failed, etc.
    current_stage = Column(String, default="Initialization")
    progress_percentage = Column(Float, default=0.0)
    priority = Column(String, default="Normal")
    assigned_models = Column(JSON, default=list) # List of active models for the job
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    artifacts = relationship("ArtifactModel", back_populates="job", cascade="all, delete-orphan")
    logs = relationship("AgentLogModel", back_populates="job", cascade="all, delete-orphan")
    metrics = relationship("MetricModel", back_populates="job", cascade="all, delete-orphan")


class ArtifactModel(Base):
    """Versioned storage for everything produced by agents (code, docs, schemas, test reports)."""
    __tablename__ = "artifacts"

    artifact_id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    artifact_type = Column(String, nullable=False) # e.g., "source_code", "architecture_doc", "test_report", "schema"
    file_path = Column(String, nullable=False)
    version = Column(Integer, default=1)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict) # Extra contextual data (tokens, creator agent)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("JobModel", back_populates="artifacts")


class AgentLogModel(Base):
    """Granular ledger of every AI interaction, prompt, response, and retry."""
    __tablename__ = "agent_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    agent_name = Column(String, nullable=False)
    model_used = Column(String, nullable=False)
    prompt_sent = Column(Text, nullable=False)
    response_received = Column(Text, nullable=False)
    execution_time_sec = Column(Float, default=0.0)
    tokens_used = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    status = Column(String, default="Success") # Success, Warning, Error
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("JobModel", back_populates="logs")


class MetricModel(Base):
    """High-frequency telemetry tracking system hardware and token metrics."""
    __tablename__ = "metrics"

    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    cpu_usage_pct = Column(Float, default=0.0)
    memory_usage_pct = Column(Float, default=0.0)
    vram_usage_mb = Column(Float, default=0.0)
    active_workers = Column(Integer, default=0)
    queue_length = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("JobModel", back_populates="metrics")