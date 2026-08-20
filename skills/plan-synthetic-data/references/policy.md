# Column Privacy Policy

## Roles

| Role | Source values in output | Training | Intended use |
| --- | --- | --- | --- |
| `public` | Allowed | Joint empirical resampling | Published or non-sensitive attributes |
| `protected` | Rare replay is constrained | Non-DP TabularARGN with value protection | Internal attributes needing practical protection |
| `private` | Audited; no direct copying path | DP TabularARGN | Sensitive or regulated attributes |
| `identifier` | Never | Excluded | Direct identifiers replaced by fresh surrogates |
| `drop` | Never | Excluded | Secrets or unusable free text |

`private` is a model-level DP guarantee for the model that generates those columns. Public and protected columns are provided as generation conditions so their output does not need to absorb DP noise.

`protected` is the conservative default for unclassified data, not a substitute for domain review. Known sensitive fields should be promoted to `private`. Identifier replacement emits strings: `uuid` provides unrelated unique values, while `sequential` provides prefixed sequence strings; neither preserves email, name, IP, card, or numeric formatting.

## Policy Shape

```json
{
  "version": 1,
  "dataset": {
    "input": "customers.parquet",
    "output": "customers.synthetic.parquet",
    "report": "customers.synthetic.report.json",
    "workspace": "customers.synthetic-workspace",
    "rows": null,
    "seed": 42
  },
  "quality": {
    "profile": "balanced",
    "max_epochs": 50,
    "max_training_minutes": 10,
    "sampling_temperature": 1.0
  },
  "privacy": {
    "default_role": "protected",
    "rare_value_threshold": 5,
    "dp": {
      "enabled": true,
      "max_epsilon": 8.0,
      "delta": 0.00001,
      "noise_multiplier": 1.5,
      "max_grad_norm": 1.0,
      "value_protection_epsilon": 1.0
    },
    "columns": {
      "country": {"role": "public"},
      "age": {"role": "protected"},
      "diagnosis": {"role": "private"},
      "birthdate": {"role": "private", "encoding": "TABULAR_DATETIME"},
      "email": {"role": "identifier", "strategy": "uuid", "prefix": "syn"},
      "internal_notes": {"role": "drop"}
    }
  },
  "acceptance": {
    "max_exact_row_replay_ratio": 0.0,
    "max_identifier_overlap_ratio": 0.0,
    "max_private_rare_value_replay_ratio": 0.0,
    "max_protected_rare_value_replay_ratio": 0.05,
    "max_mean_numeric_ks": 0.2,
    "max_column_numeric_ks": 0.3,
    "max_mean_categorical_tv": 0.2,
    "max_column_categorical_tv": 0.3,
    "max_mean_text_length_ks": 0.2,
    "max_column_text_length_ks": 0.3,
    "max_mean_text_tfidf_distance": 0.35,
    "max_column_text_tfidf_distance": 0.5,
    "max_mean_missing_rate_delta": 0.1,
    "max_column_missing_rate_delta": 0.15,
    "max_mean_abs_correlation_delta": 0.25,
    "max_correlation_delta": 0.4,
    "max_propensity_auc": 0.8,
    "columns": {
      "age": {"max_numeric_ks": 0.15},
      "diagnosis": {"max_rare_value_replay_ratio": 0.0}
    }
  }
}
```

## Quality Profiles

- `fast`: smoke tests and iteration. Do not use its output for release decisions.
- `balanced`: default production candidate.
- `high`: longer training for difficult mixed-type tables.

Explicit `max_epochs` and `max_training_minutes` override profile defaults.

Use `encoding` when a physical dtype does not express the column's semantics. The planner infers `TABULAR_DATETIME` for datetime dtypes and sufficiently parseable date-like strings; review that decision and override ambiguous values with `--encoding COLUMN=TYPE`.

## Differential Privacy

Lower epsilon means stronger privacy and usually lower utility. `max_epsilon` is a hard ceiling, not a target. The generator records the checkpoint epsilon reported by the engine. Never describe a run as DP if the engine did not produce a DP checkpoint and a recorded epsilon/delta.

DP protects participation in the private-stage training data. It does not make deliberately public columns private, repair a bad role assignment, or authorize releasing identifiers.

## Acceptance Gates

Quality thresholds are dataset-specific starting points. Identifier overlap, dropped-column presence, and DP evidence are hard gates. Do not relax a privacy gate merely to make a run pass.

Use global maximum-column gates to prevent a poor field from hiding inside a good average. Add stricter user requirements with `--acceptance NAME=VALUE` and `--column-requirement COLUMN.METRIC=VALUE`. Supported column metrics are `max_numeric_ks`, `max_categorical_tv`, `max_missing_rate_delta`, and `max_rare_value_replay_ratio` (protected/private only).

Columns explicitly encoded as `TABULAR_CHARACTER` use `max_text_length_ks` and
`max_text_tfidf_distance` instead of `max_categorical_tv`. The global text gates cover both mean and worst-column
values. TF-IDF measures lexical fidelity rather than meaning, factuality, or coherence.
