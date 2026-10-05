"""Reviewed operational-only source revisions compatible with existing inputs.

These exact hashes are not a wildcard exemption. Actual prompt/source provenance
still records the deployed bytes; unknown revisions invalidate prior results.
2026-09-25 report change: imports, halt-exception tuple and two except clauses only.
AST comparison against the prior image confirmed identical remaining code.
"""
COMPATIBLE_INPUT_HASHES = {
    'assembled/report_generator': {
        '6d385528facb08ab529993b23a8ff0b5e85b6b8a422bb9c1e512734fad150904':
            '858766646b10215c3e81380be3d51b0baa623687fe2fb35b2cafa5c20dfacc09',
    },
}


# 2026-09-29: plan identity is projected into title metadata only. Existing
# facts, DAC scores and narrative bodies stay byte-for-byte unchanged. The
# extraction instruction applies to future uploads; their changed stored
# facts still invalidate snapshots normally. This exact compatibility keeps
# title/layout repair from requesting a costly full evaluation regeneration.
COMPATIBLE_INPUT_HASHES.setdefault('assembled/project_overview', {})['bc5be752401e9a20fceb3046ce2c89070275c73a1b326d15f7699586d8289e63'] = '3c15f91d7f55ee99d21a04bce1399f44aaa358b37783b5579b68d85aeb2e3148'
COMPATIBLE_INPUT_HASHES.setdefault('assembled/report_generator', {})['cdc9b9ea0043c51edbc9523eff0c258f4d397e3d93f7245dfc742b6de167147e'] = '95b11030dd030e370559d9589ac0b48a8bc4dd577545361e53109c57ffbd461e'
COMPATIBLE_INPUT_HASHES.setdefault('foundation_overview_facts', {})['ecab2ddce06f81f249fb38d2eca8bb5b2ac0f0b72faab7929cb3bf5f0bcc6577'] = 'bd7c2f771bbc6726e57d681c00ce51a65e7a38885c56399d8a9875385a01c3a1'


def compatible_input_manifest(manifest):
    return {name:COMPATIBLE_INPUT_HASHES.get(name, {}).get(value, value)
            for name,value in manifest.items()}


# V2.4.13 changes cover metadata only: plan profile -> five cover slots. The
# cover is projected from the current profile for reads and exports, so no old
# cover survives this compatibility. DAC and narrative generation are unchanged.
COMPATIBLE_INPUT_HASHES.setdefault('assembled/report_generator', {})['7e12d3d7a2be1ee606e8f3ec945394be0130e8aaee3f55b1c9c2e24a34fe2e22'] = '95b11030dd030e370559d9589ac0b48a8bc4dd577545361e53109c57ffbd461e'
COMPATIBLE_INPUT_HASHES.setdefault('shared/Section1_표지.py', {})['a4b625972944ed00f702ad30f1b6b71ae672c012a4d7dec618df151faed9e6d3'] = '85e80997ea492dff15ea4eb0f3dd86b18988f478813780ac218c5b0ce278422a'

# V2.4.16: bounded recheck of invalid intake exclusion proposals only. Existing
# stored documents, mappings and assessments are untouched. Changed exclusions
# on explicitly reprocessed documents still invalidate their dependent inputs.
COMPATIBLE_INPUT_HASHES.setdefault('assembled/intake_triage', {})['0c07cb9dcd5abb788d745e8e5edca9075e957035f68717fc245238578ec13eea'] = '8f23cedec34a1a9f68494c204db085e8b39e85464949998e2f4363595e70dc88'
