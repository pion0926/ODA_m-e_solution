from unittest.mock import patch
import pytest
from kodame_intake.pdm_monitoring import _select_pdm_source
from kodame_intake.document_classification import NoPdmSource


def test_existing_validated_snapshot_survives_content_classifier_upgrade():
    doc={'id':'old-source','original_name':'unrelated-name.hwp','analysis':{},'queue_position':1}
    slots={'outcome_indicator':'1. 기존에 검증된 원문 지표'}
    with patch('kodame_intake.pdm_monitoring.connection') as connection:
        connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={
            'source_document_id':'old-source','model':{'source_cells':slots}}
        assert _select_pdm_source([doc])==(doc,slots)


@pytest.mark.parametrize('doc', [
    {'id':'different-source','analysis':{},'queue_position':1},
    {'id':'old-source','analysis':{'content_classification':{'is_pdm_source':False}},'queue_position':1},
])
def test_never_guesses_replacement_or_overrides_new_negative_classification(doc):
    with patch('kodame_intake.pdm_monitoring.connection') as connection:
        connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={
            'source_document_id':'old-source','model':{'source_cells':{'outcome_indicator':'1. old'}}}
        with pytest.raises(NoPdmSource):_select_pdm_source([doc])
