# DCML rollback and recovery

Every candidate retains pre/post hashes and the prior active checkpoint. Promotion requires a passing held-out canary and signed promotion. Rollback requires a signed action and restores the selected prior checkpoint after marking the current policy rolled back. SQLite backup/restore and integrity checks continue to preserve all migrations.
