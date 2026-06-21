def manual_check_task(query: str = ''):
    return {'status': 'manual_check_required', 'query': query, 'no_fake_results': True}
