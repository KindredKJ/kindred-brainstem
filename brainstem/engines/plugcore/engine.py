import platform, shutil
from brainstem.utils.paths import GENERATED
from brainstem.utils.yaml_io import write_yaml

def scan():
    profile={'host_type':'local_machine','os':platform.system(),'cpu':platform.processor() or platform.machine(),'python':platform.python_version(),'available_tools':{t: bool(shutil.which(t)) for t in ['git','python','docker']},'access_levels':['observe','suggest','execute_soft'],'execute_hard':'founder_approval_required'}
    scores={'compute_score':60,'interface_score':50,'network_score':40,'storage_score':60,'sensor_score':10,'actuator_score':0,'safety_score':90,'permission_score':70,'result_execution_score':70,'overall_safe_potential_score':55}
    d=GENERATED/'plugcore'; d.mkdir(parents=True,exist_ok=True)
    write_yaml(d/'host_profile.yaml', profile); write_yaml(d/'max_potential_plan.yaml', scores); write_yaml(d/'capability_graph.yaml', {'capabilities':profile['available_tools']}); write_yaml(d/'resource_envelope.yaml', {'local_first':True}); write_yaml(d/'safe_action_map.yaml', {'execute_hard':'approval_required'})
    (d/'utilization_report.md').write_text('# PlugCore Utilization Report\n\nNext required actions: keep execution local and approval-gated.\n', encoding='utf-8')
    return profile
