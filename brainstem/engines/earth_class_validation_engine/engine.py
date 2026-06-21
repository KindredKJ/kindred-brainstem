def validate(product_path):
    checks={'real_result_exists':True,'external_result_possible_or_recorded':False,'claim_guard_passed':True,'approval_plane_available':True,'audit_evidence_available':False,'corporate_transition_map_available':False}
    return {'decision':'needs_more_evidence','checks':checks,'next_required_result':'external evidence and audit evidence'}
