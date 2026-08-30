# DCML governed learning lifecycle

The allowed forward lifecycle is:

```text
OBSERVED -> PROPOSED -> EVALUATED -> APPROVED -> PROMOTED -> ACTIVE
```

Terminal or corrective states are `REJECTED`, `CONFLICTED`, `ROLLED_BACK`, and `SUPERSEDED`. Every transition is validated and emitted to the audit log. Skipping evaluation or approval raises an error. Consequential promotion requires an approval record naming the founder authority.

A proposal contains its kind, structured payload, provenance, evaluation, approval identifier, revision, and optional supersession reference. Promotion materializes a candidate memory, strategy, procedure, skill, or routing policy. Materialized records do not affect selection until `ACTIVE`. Rejection creates no behavioral record. Rollback removes the record from active selection while preserving its history.

No lifecycle state modifies foundation-model weights. `ReferenceDatasetBuilder` exports only experiences explicitly marked approved for training, creates a versioned train/evaluation split, labels the dataset `REFERENCE_ONLY`, and reports `parameter_training_performed: false`.
