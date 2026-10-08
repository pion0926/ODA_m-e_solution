from kodame_intake.evaluation_identity import evaluator_identity


def document(tmp_path, name, text):
    path = tmp_path / (name + '.txt')
    path.write_text(text, encoding='utf-8')
    return {'original_name': name, 'extracted_path': str(path)}


def test_historical_project_manager_is_not_current_evaluator(tmp_path):
    row = document(tmp_path, '4차년도 자체평가결과보고서.pdf', '확인자 사업책임자 홍길동 (인)\n제출: 2025. 6. 한국대학교')
    assert not evaluator_identity([row])['evaluation_manager']
    assert not evaluator_identity([row])['evaluation_institution']


def test_past_evaluation_cover_is_not_current_commission(tmp_path):
    row = document(tmp_path, '2024 종료평가 결과보고서.pdf', '평가책임자: 홍길동\n평가수행기관: 평가기관')
    assert not evaluator_identity([row])['evaluation_manager']


def test_explicit_evaluator_roles_in_commission_are_retained(tmp_path):
    row = document(tmp_path, '종료평가 수행계획서.pdf', '평가책임자: 김평가\n평가수행기관: 외부평가연구원')
    result = evaluator_identity([row])
    assert result['evaluation_manager'] == '김평가'
    assert result['evaluation_institution'] == '외부평가연구원'
    assert result['evaluation_identity_source'] == row['original_name']


def test_unassigned_or_wrong_roles_not_promoted(tmp_path):
    row = document(tmp_path, '최종평가 실시계획서.pdf', '사업책임자: 홍길동\n사업수행기관: 한국대학교\n평가책임자: 미정\n평가수행기관: 확인 필요')
    result = evaluator_identity([row])
    assert not result['evaluation_manager'] and not result['evaluation_institution']


def test_missing_file_does_not_block_report():
    result = evaluator_identity([{'original_name': '종료평가 수행계획서.pdf'}])
    assert not result['evaluation_manager']
