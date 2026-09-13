"""Read-only reproduction: schema key is mistaken for a factual agency claim."""
import json
from kodame_intake.report_generator import _validate_reader_content

value='(사업 추진배경) 우즈베키스탄 응급의료 교육 수요와 현지 전문인력 양성의 필요성을 사업 문헌에 근거하여 검토함. '*8
slots={k:value for k in ['mdg_maternal_health_context','government_policy_context','target_region_need','koica_policy_alignment','project_selection_rationale']}
scope={'commissioning_agency':'한국연구재단','project_status':'ongoing'}
serialized=json.dumps({'schema':'section6_project_background_slots_v1','slots':slots},ensure_ascii=False)
body='\n'.join(slots.values())
checks={name:[i for i in _validate_reader_content('project-background',text,'우즈베키스탄',scope) if 'KOICA' in i] for name,text in [('json_with_required_key',serialized),('values_only',body)]}
print(json.dumps(checks,ensure_ascii=False))
assert not checks['json_with_required_key'] and not checks['values_only']
