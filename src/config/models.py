"""Pydantic models for the firm config schema (CLAUDE.md section 8 / BUILD_PLAN.md Step 4).

The engine reads these config values; it never reads a firm name to decide
behaviour (CLAUDE.md section 3.1) — everything a firm's methodology could
differ on is expressed here, as data, not as branches in src/compute or
src/graph. An invalid config must fail loudly at load time (CLAUDE.md
section 8), which is what pydantic's validation gives us for free.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NumberPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decimals: int = Field(ge=0, le=10)
    rounding: Literal["ROUND_HALF_UP", "ROUND_DOWN"]


class UtilizationPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["percent", "basis_points"]
    decimals: int = Field(ge=0, le=10)
    rounding: Literal["ROUND_HALF_UP", "ROUND_DOWN"]


class PresentationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utilization: UtilizationPresentation
    percentage: NumberPresentation
    duration: NumberPresentation
    currency: NumberPresentation


class FieldMatch(BaseModel):
    """One predicate against a Position's own field, or a field on the
    Issuer/AssetClass it's linked to in the graph.

    Exactly one of `equals` / `in_values` / `below_investment_grade` must be
    set — enforced below so a config author can't write a match that
    silently matches nothing (or everything).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field: Literal["asset_class", "credit_rating", "issuer_type", "issuer_name", "parent_issuer"]
    equals: str | None = None
    in_values: list[str] | None = Field(default=None, alias="in")
    below_investment_grade: bool | None = None

    @model_validator(mode="after")
    def _exactly_one_predicate(self) -> "FieldMatch":
        predicates = (self.equals, self.in_values, self.below_investment_grade)
        set_count = sum(p is not None for p in predicates)
        if set_count != 1:
            raise ValueError(
                f"FieldMatch for field={self.field!r} must set exactly one of "
                f"'equals', 'in', 'below_investment_grade' (got {set_count})"
            )
        return self


class IncludeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: FieldMatch


class AggregateFigureConfig(BaseModel):
    """A figure computed by summing every Position matching any include rule."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["aggregate"] = "aggregate"
    include: list[IncludeRule] = Field(min_length=1)
    limit_ref: str


class ConcentrationFigureConfig(BaseModel):
    """A figure computed by grouping matching Positions and taking the largest group."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["concentration"] = "concentration"
    filter: FieldMatch
    group_by: Literal["issuer_name", "parent_issuer"]
    limit_ref: str


FigureConfig = Annotated[
    Union[AggregateFigureConfig, ConcentrationFigureConfig],
    Field(discriminator="kind"),
]


class FirmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    presentation: PresentationConfig
    figures: dict[str, FigureConfig]
