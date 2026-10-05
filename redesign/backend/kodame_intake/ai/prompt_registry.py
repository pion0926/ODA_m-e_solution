"""Named, reviewable prompts with content fingerprints for provenance."""
import hashlib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent/'prompts'

@lru_cache(maxsize=32)
def load_prompt(name):
    if not name.replace('_','').isalnum():
        raise ValueError('Invalid prompt name')
    return (ROOT/f'{name}.md').read_text(encoding='utf-8')

@lru_cache(maxsize=1)
def prompt_manifest():
    files = {p.stem:p for p in sorted(ROOT.glob('*.md'))}
    # Some structured prompts are still assembled next to their schemas. Keep
    # those implementations in provenance until their final extraction too.
    service = ROOT.parent.parent
    for name in ('report_generator','pdm_evidence','dac_evidence','dac_assessor',
                 'evidence_matching','project_overview','artifact_registration',
                 'intake_triage','report_content_policy','report_review_policy',
                 'report_performance','evaluation_identity'):
        path = service / (name+'.py')
        if path.is_file():
            files['assembled/'+name] = path
    shared = next((p/'prompts' for p in ROOT.parents
                   if (p/'prompts/performance_risk_policy.md').is_file()), None)
    if shared:
        files.update({'shared/'+p.name:p for p in sorted(shared.iterdir())
                      if p.suffix == '.py' or p.name == 'performance_risk_policy.md'})
    return {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
