"""Small polling read models; analysis caches remain available to explicit reviews."""

# Listing does not need source excerpts, DAC full-text caches, measurement caches,
# or registration fact bodies. Keep the public serializer contract unchanged.
INTAKE_LIST_COLUMNS = """
    id,original_name,size_bytes,sha256,upload_role,evaluation_excluded,evaluation_scope,
    extracted_path,status,stage,progress,cancel_requested,analysis_model,intake_mode,
    triage,queue_position,summary,error_code,error_message,uploaded_at,updated_at,
    jsonb_build_object(
        'intake_mode',analysis->'intake_mode',
        'evidence_matches',coalesce(analysis->'evidence_matches','{}'::jsonb),
        'registration',analysis->'registration',
        'quality_flags',coalesce(analysis->'quality_flags','[]'::jsonb)
    ) AS analysis,
    CASE WHEN jsonb_typeof(analysis#>'{registration_facts,facts}')='array'
         THEN jsonb_array_length(analysis#>'{registration_facts,facts}')
         ELSE 0 END AS registration_fact_count
"""

# Purpose-policy checks use these fields only, including legacy manual override
# detection. Do not fetch each document's unrelated DAC/measurement source caches.
PDM_DOCUMENT_COLUMNS = """
    id,original_name,size_bytes,summary,
    jsonb_build_object(
        'pdm_mapping_overrides',analysis->'pdm_mapping_overrides',
        'evidence_matches',jsonb_build_object(
            'version',analysis#>'{evidence_matches,version}',
            'sources',coalesce(analysis#>'{evidence_matches,sources}','{}'::jsonb),
            'pdm',coalesce(analysis#>'{evidence_matches,pdm}','[]'::jsonb)
        )
    ) AS analysis
"""


def public_monitoring(monitoring):
    """Pair bodies are a server-side incremental ledger, never a polling payload."""
    return {key: value for key, value in (monitoring or {}).items() if key != 'pair_results'}
