def ask(task, text):
    return {'task':task,'model':'rule_model','response':f'Local rule-model summary for {task}: {text}. No paid API or external key used.','next_required_result':'verify with local evidence'}
