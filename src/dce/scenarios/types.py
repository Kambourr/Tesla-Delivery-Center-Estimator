"""Frozen data carried by the scenario layer.

``dce.model.types.Scenario`` holds the operating shocks the static cost model
and the DCF already understand (wage, rent, deliveries). The DCF knobs a
scenario also needs (discount rate, horizon, growth, fee) live here in
:class:`DcfShocks`, and :class:`NamedScenario` ties both to a stable
``scenario_id`` so results can be keyed, compared, and charted. The model
package never imports this module.

Everything here is plain data: strings, floats, ints, tuples, and frozen
dataclasses. The app can chart a :class:`TornadoBar` list or dump it to JSON
without matplotlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dce.model.types import EstimateResult, Scenario


@dataclass(frozen=True)
class DcfShocks:
    """Absolute replacements for :class:`dce.model.dcf.DcfInputs` fields.

    ``None`` keeps the base value. Values are absolute, not fractional:
    ``discount_rate=0.163`` means a 16.3% WACC, ``growth=0.0`` means no
    post-ramp growth. Apply with :func:`dce.scenarios.grid.apply_dcf_shocks`.
    """

    discount_rate: float | None = None
    horizon_years: int | None = None
    growth: float | None = None
    fee_per_delivery: float | None = None


@dataclass(frozen=True)
class NamedScenario:
    """One what-if case with a stable id, a display label, and its DCF shocks."""

    scenario_id: str
    label: str
    scenario: Scenario
    dcf: DcfShocks = field(default_factory=DcfShocks)


@dataclass(frozen=True)
class ScenarioResult:
    """A :class:`NamedScenario` and the estimate it produced."""

    named: NamedScenario
    result: EstimateResult

    @property
    def scenario_id(self) -> str:
        return self.named.scenario_id


@dataclass(frozen=True)
class TornadoBar:
    """One one-at-a-time sensitivity bar of NPV.

    ``npv_low`` <= ``npv_base`` <= ``npv_high`` whenever NPV is monotone in the
    driver over its range. ``input_at_npv_low`` and ``input_at_npv_high`` are
    the driver values (in ``unit``) that produced each end, so a chart can
    label both ends. ``swing`` is ``npv_high - npv_low``.
    """

    driver: str
    label: str
    unit: str
    input_base: float
    input_at_npv_low: float
    input_at_npv_high: float
    npv_low: float
    npv_base: float
    npv_high: float
    swing: float


__all__ = ["DcfShocks", "NamedScenario", "ScenarioResult", "TornadoBar"]
