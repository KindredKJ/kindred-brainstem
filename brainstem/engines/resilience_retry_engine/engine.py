def retry_plan(action): return {'action':action,'policy':'local_safe_retry','max_attempts':3,'dead_letter_on_failure':True}
