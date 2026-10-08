from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from kodame_intake.api import project_routes


def source(document_id, role):
    return dict(id=document_id, original_name=f'{document_id}.pdf',
                size_bytes=100, summary='summary', upload_role=role)


def overview_result(source_ids, documents, *, completed=True):
    row = dict(id='overview', run_id=None, model='test', document_count=1,
               source_document_ids=source_ids,
               overview={'project_name': {'text': 'Plan project', 'source_refs': ['D001']}},
               conflicts=[], created_at=datetime.now(timezone.utc))
    with patch.object(project_routes, 'latest_plan_overview', return_value=row if completed else None), \
            patch.object(project_routes, 'connection') as connection:
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = source('latest-pdm', 'pdm')
        conn.execute.return_value.fetchall.return_value = documents
        return project_routes.project_overview()


def test_basic_info_links_actual_plan_even_when_other_plan_and_pdm_exist():
    result = overview_result(['used-plan'], [source('other-plan', 'project_plan'),
                                            source('latest-pdm', 'pdm'),
                                            source('used-plan', 'project_plan')])
    assert result['project_plan_source_document']['id'] == 'used-plan'
    assert result['project_plan_source_document'] == result['sources']['project_name'][0]
    assert result['pdm_source_document']['id'] == 'latest-pdm'


def test_pdm_only_or_replaced_plan_does_not_claim_a_generated_overview():
    result = overview_result([], [source('latest-pdm', 'pdm')], completed=False)
    assert result['status'] == 'not_generated'
    assert result['project_plan_source_document'] is None
    assert result['pdm_source_document']['id'] == 'latest-pdm'


@pytest.mark.parametrize('documents', [[], [source('used-source', 'pdm')],
                                      [source('used-source', 'evidence')]])
def test_missing_or_wrong_role_source_never_falls_back_to_pdm(documents):
    result = overview_result(['used-source'], documents)
    assert result['project_plan_source_document'] is None

