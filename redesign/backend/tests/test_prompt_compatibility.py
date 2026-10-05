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
