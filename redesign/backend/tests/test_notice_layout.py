from kodame_intake.hwpx_layout.notice import repair_notice_boxes


def test_nested_disclaimer_height_does_not_squeeze_changed_text():
    inner='<hp:tbl noAdjust="0"><hp:sz width="45000" height="6000"/><hp:pos affectLSpacing="0"/><hp:tr><hp:tc><hp:subList vertAlign="CENTER"><hp:p paraPrIDRef="3"><hp:run charPrIDRef="34"><hp:t>본 보고서는 등록된 '+('근거자료 검토 ' * 35)+'</hp:t></hp:run></hp:p></hp:subList><hp:cellSz width="45000" height="282"/></hp:tc></hp:tr></hp:tbl>'
    source='<hp:tbl xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:tr><hp:tc><hp:subList><hp:p><hp:run>'+inner+'</hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>'
    fixed,count=repair_notice_boxes(source)
    assert count==1
    assert 'height="282"' not in fixed
    assert 'affectLSpacing' not in fixed
    assert fixed.count('<hp:tbl')==1
    assert fixed.count('근거자료 검토')==35
