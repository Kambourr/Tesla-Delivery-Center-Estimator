# M3 model fixtures

- `m3_frozen_inputs.json` — synthetic, round-number demand and resolved-cost
  inputs (rent, wage, energy and demand rates) plus three scenarios. Not
  sourced from any dataset and not Tesla data.
- `golden_m3.json` — expected outputs for those inputs under the shipped
  `data/defaults/assumptions.yaml`. It records the `assumptions_version` it
  was built from.

`tests/unit/model/test_golden.py` checks `$/delivery` to 2 decimals,
components to half a cent, and driver order and shares. It also re-derives
the base case with plain arithmetic so the golden is not only the model
checking itself.

## Regenerating the golden

Only on purpose: after a formula change, or after editing a default value
and bumping `assumptions_version`. Then review the JSON diff.

```bash
DCE_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/unit/model/test_golden.py
# or: make test DCE_UPDATE_GOLDEN=1
```

If you change a default, also update the hand-arithmetic test, which hard
codes the 2026.11.0 values.
