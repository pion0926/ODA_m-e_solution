from kodame_intake.ai.prompt_compatibility import compatible_input_manifest, COMPATIBLE_INPUT_HASHES


def test_only_reviewed_exact_operational_revision_is_compatible():
    revisions=COMPATIBLE_INPUT_HASHES['assembled/report_generator']
    new,old=next(iter(revisions.items()))
    source={'assembled/report_generator':new,'other':new}
    assert compatible_input_manifest(source)=={'assembled/report_generator':old,'other':new}
    assert source['assembled/report_generator']==new  # provenance remains exact


def test_unknown_revision_and_other_prompt_change_still_invalidate():
    new,old=next(iter(COMPATIBLE_INPUT_HASHES['assembled/report_generator'].items()))
    assert compatible_input_manifest({'assembled/report_generator':'new-prompt'}) != compatible_input_manifest({'assembled/report_generator':new})
    assert compatible_input_manifest({'assembled/report_generator':old}) == compatible_input_manifest({'assembled/report_generator':new})


def test_v31_reader_guard_only_fix_preserves_v30_evaluation_input_identity():
    from kodame_intake.evaluation_versions import digest
    old = '341c9080e3447b7c690e77e31de2712931603a91f60abace9ebf5cf58de46b73'
    new = '8ac4b134943bf48a9482a06c65800ac76cb3b0a77b7a30d6e002fed90b59012e'
    before = {'assembled/report_generator': old, 'assembled/dac_assessor': 'same-dac-policy'}
    deployed = {**before, 'assembled/report_generator': new}
    inputs = {'overview': {'name': '합성 사업'}, 'pdm': {'indicators': []}, 'rubric': 'same-rules'}
    prior_digest = digest({**inputs, 'prompts': compatible_input_manifest(before)})
    current_digest = digest({**inputs, 'prompts': compatible_input_manifest(deployed)})
    assert prior_digest == current_digest
    assert deployed['assembled/report_generator'] == new  # Do not rewrite actual deployment provenance.
    for changed in (
        {**deployed, 'assembled/dac_assessor': 'changed-dac-policy'},
        {**deployed, 'assembled/report_generator': 'unreviewed-future-revision'},
    ):
        assert digest({**inputs, 'prompts': compatible_input_manifest(changed)}) != prior_digest
    assert digest({**inputs, 'rubric': 'changed-rules', 'prompts': compatible_input_manifest(deployed)}) != prior_digest


def test_v31_compatibility_does_not_apply_the_hash_to_another_prompt():
    new = '8ac4b134943bf48a9482a06c65800ac76cb3b0a77b7a30d6e002fed90b59012e'
    assert compatible_input_manifest({'assembled/dac_assessor': new}) == {'assembled/dac_assessor': new}
