from kodame_intake.presentation_quality import missing_rendered_content


def test_wrapped_table_cells_use_alternate_pdf_reading_order():
    required = ["행정 승인·통관 지연으로 일정 부담이 발생함",
                "행정 소요를 반영하고 위험대장을 관리해야 함"]
    poppler = "행정 승인 · 통관 지연으로 일정 부담이 행정 소요를 반영하고\n발생함\n위험대장을 관리해야 함"
    stream = "행정 승인 · 통관 지연으로 일정 부담이\n발생함\n행정 소요를 반영하고\n위험대장을 관리해야 함"
    assert missing_rendered_content(required, [poppler]) == required
    assert missing_rendered_content(required, [poppler, stream]) == []


def test_real_omission_or_scattered_words_still_fail():
    sentence = "행정 소요를 반영하고 위험대장을 관리해야 함"
    assert missing_rendered_content([sentence], ["행정 소요를 반영하고", "위험대장을 관리해야 함"]) == [sentence]
    assert missing_rendered_content([sentence], ["위험대장을 관리해야 함. 행정 소요를 반영하고"]) == [sentence]
