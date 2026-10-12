"""Response shapes of the read-only /api/v1 JSON API.

The handlers build their JSON by hand (json.dumps with default=str) and return
a Response, so these models document the contract in /openapi.json without
re-serialising or changing any payload.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Column(BaseModel):
    name: str
    type: str
    notnull: bool
    pk: bool


class SchemaOut(BaseModel):
    schema_version: str
    tables: dict[str, list[Column]]


class TableOut(BaseModel):
    schema_version: str
    table: str
    row_count: int
    rows: list[dict[str, Any]]


class DemoCredentialsOut(BaseModel):
    username: str
    password: str
    logouts_allowed: int


class MetricDef(BaseModel):
    metric: str
    label: str
    version: Any
    aggregation: str
    owner: str
    unit: str
    dimensions: list[str]


class MetricsOut(BaseModel):
    schema_version: str
    count: int
    metrics: list[MetricDef]


class MetricOut(BaseModel):
    schema_version: str
    metric: str
    value: Any
    by: str | None
    unit: str
    receipt: dict[str, Any]


class ForecastPoint(BaseModel):
    date: str
    litres: float


class YieldForecastOut(BaseModel):
    schema_version: str
    model: str
    model_version: Any
    cow_id: int
    tag: str
    breed: str
    trained_through: str
    forecast: list[ForecastPoint]
