# Strata Data Port client rollback

Stop the local runtime, back up `~/.kindred/brainstem.db` and its WAL/SHM files, then revert the feature commit. Migration 3 is additive; do not drop its tables during rollback. Restore the database only while the runtime is stopped and run SQLite `PRAGMA integrity_check` before restart. Remove mTLS environment configuration if the boundary client is disabled; never delete certificate or key material without its separate recovery process.
