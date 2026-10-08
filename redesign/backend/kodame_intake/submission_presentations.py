"""Editable supplementary decks using the service's existing PPT renderer."""
from datetime import datetime
from zoneinfo import ZoneInfo
from copy import deepcopy
from io import BytesIO
import re
from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor
from backend.oda_me.hwpx.patchers import parse_lesson_items
from .submission_exports import TEMPLATES, feedback_records, FEEDBACK_HEADERS
from .presentation_reference_renderer import text, lines


def _leaves(shapes):
    for shape in shapes:
        if hasattr(shape, 'shapes'):
            yield from _leaves(shape.shapes)
        elif shape.has_text_frame:
            yield shape


def _fit(shape, value, maximum=12, minimum=7):
    frame = shape.text_frame
    width = max(15, (shape.width-frame.margin_left-frame.margin_right)/12700)
    height = max(10, (shape.height-frame.margin_top-frame.margin_bottom)/12700)
    size = maximum
    while size > minimum and lines(value, width, size)*size*1.22 > height:
        size -= .5
    if lines(value, width, size)*size*1.22 > height:
        raise ValueError('교훈 PPT 양식의 텍스트 공간을 초과했습니다. 교훈 본문을 간결하게 수정해 주세요.')
    # Reuse the shape and template style; only replace the paragraph content.
    frame.clear(); frame.word_wrap=True
    frame.paragraphs[0].text=str(value)
    for p in frame.paragraphs:
        p.font.name='나눔고딕';p.font.size=Pt(size);p.space_after=Pt(0);p.line_spacing=1.1
        p.font.color.rgb=RGBColor.from_string('FFFFFF')


def lesson_deck(title, content, references):
    lessons = parse_lesson_items(content)
    if not lessons or len(lessons)>9:
        raise ValueError('교훈 1~9개가 필요합니다. 저장된 교훈 본문을 확인해 주세요.')
    prs = Presentation(TEMPLATES/'forms/5-3. 분야별 평가 교훈 리포트 양식.pptx')
    refs='\n'.join(name if len(name)<=90 else name[:89]+'…' for name in references[:2])
    refs=(refs+'\n' if refs else '')+'전체 근거자료: 발표자 노트와 본 보고서의 교훈·관련 평가 절 참조'
    for slide in prs.slides:
        for shape in _leaves(slide.shapes):
            value=shape.text.strip()
            if value.startswith('2023'):
                _fit(shape, '분야별 평가 교훈 리포트\n종료평가의 주요 교훈과 적용 조건', 16, 12)
            elif '[예시]' in value:
                shape.top += Pt(10)
                shape.height -= Pt(10)
                _fit(shape, f'{title}\n저장된 종료평가 보고서의 교훈 {len(lessons)}건과 후속 사업 점검 질문을 정리함. 적용 조건과 근거의 한계는 각 교훈 및 본 보고서의 해당 절을 참조함.', 10, 8)
            elif 'I. 개요' in value:
                shape.width=Pt(480);shape.height=Pt(20)
                shape.text_frame.margin_top=shape.text_frame.margin_bottom=0
                _fit(shape,'I. 개요 (OVERVIEW)',12,11)
            elif 'http://koica.go.kr' in value:
                _fit(shape, refs, 7, 7)
            elif value.startswith('발간 날짜:'):
                _fit(shape, f'작성일: {datetime.now(ZoneInfo("Asia/Seoul")):%Y.%m.%d}\n평가자: 확인 필요', 8, 7)
        slide.notes_slide.notes_text_frame.text = '저장된 교훈 원문\n'+content+'\n근거자료\n'+'\n'.join(references)
    groups=[]
    for shape in prs.slides[0].shapes:
        if hasattr(shape,'shapes'):
            children=list(_leaves(shape.shapes))
            if any(c.text.strip().startswith('설명 설명') for c in children):
                groups.append((shape, children))
    # The source has nine narrow sample cards. Long real lessons cannot fit in
    # them legibly. Keep its master/branding/overview/references, flow full text
    # in a wide column and repeat the same template page when needed.
    for shape,_children in groups:
        shape._element.getparent().remove(shape._element)
    first=prs.slides[0]
    pages=[[]];used=0
    for i,item in enumerate(lessons,1):
        body=item['lesson']
        paragraphs=[]
        while len(body)>1150:
            cut=body.rfind(' ',0,1150)
            if cut<500:cut=1150
            paragraphs.append(body[:cut]);body=body[cut:].lstrip()
        paragraphs.append(body)
        for n,body in enumerate(paragraphs):
            label=f"{i:02}. {item['observation']}"+(' (계속)' if n else '')
            title_h=max(22,lines(label,492,12)*15)
            body_h=max(20,lines(body,492,11)*14)
            height=title_h+body_h+18
            if pages[-1] and used+height>435:
                pages.append([]);used=0
            pages[-1].append((label,body,title_h,body_h));used+=height
    slides=[first]
    for _ in pages[1:]:
        slide=prs.slides.add_slide(first.slide_layout)
        for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
        mapping={}
        for rel in first.part.rels.values():
            if rel.reltype.endswith(('/slideLayout','/notesSlide')):continue
            mapping[rel.rId]=slide.part.relate_to(rel.target_ref if rel.is_external else rel.target_part,rel.reltype,rel.is_external)
        for shape in first.shapes:
            element=deepcopy(shape._element)
            for node in element.iter():
                for key,value in list(node.attrib.items()):
                    if key.startswith('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}') and value in mapping:
                        node.set(key,mapping[value])
            slide.shapes._spTree.insert_element_before(element,'p:extLst')
        bg=first._element.cSld.find('{http://schemas.openxmlformats.org/presentationml/2006/main}bg')
        if bg is not None:slide._element.cSld.insert(0,deepcopy(bg))
        sid=prs.slides._sldIdLst[-1];prs.slides._sldIdLst.remove(sid);prs.slides._sldIdLst.insert(len(prs.slides._sldIdLst)-1,sid)
        slides.append(slide)
    for page_no,(slide,items) in enumerate(zip(slides,pages),1):
        y=225
        for label,body,title_h,body_h in items:
            text(slide,23,y,494,title_h,label,12,True,'FFFFFF');y+=title_h
            text(slide,23,y,494,body_h,body,11,color='FFFFFF');y+=body_h+18
        for shape in _leaves(slide.shapes):
            if re.fullmatch(r'-\d+-',shape.text.strip()):_fit(shape,f'-{page_no}-',8,7)
        slide.notes_slide.notes_text_frame.text='저장된 교훈 원문\n'+content+'\n근거자료\n'+'\n'.join(references)
    checklist=[]
    for i,item in enumerate(lessons,1):
        # Preserve each lesson's questions as one row, including multiple lines.
        checklist.append((str(i),item['checklist'],''))
    for shape in prs.slides[-1].shapes:
        if shape.has_text_frame and re.fullmatch(r'-\d+-',shape.text.strip()):_fit(shape,f'-{len(prs.slides)}-',8,7)
        if not shape.has_table or len(shape.table.columns)!=3:
            continue
        table=shape.table
        for row in range(1,len(table.rows)):
            values=checklist[row-1] if row<=len(checklist) else ('','','')
            for col,value in enumerate(values):
                table.cell(row,col).text=value
                for p in table.cell(row,col).text_frame.paragraphs:
                    p.font.name='나눔고딕';p.font.size=Pt(10);p.line_spacing=1.1
                    p.font.color.rgb=RGBColor.from_string('FFFFFF')
    out=BytesIO();prs.save(out);return out.getvalue()


def feedback_deck(title, content):
    records=feedback_records(title,content)
    prs=Presentation();prs.slide_width=Pt(960);prs.slide_height=Pt(540)
    # A separate presentation derived from all 12 columns of official form 5-4.
    # Split long values across slides instead of clipping or shrinking to unreadable text.
    for record in records:
        fields=list(zip(FEEDBACK_HEADERS[2:],record[2:]))
        chunks=[];current=[];height=0
        for label,value in fields:
            value=str(value)
            pieces=[value[i:i+450] for i in range(0,len(value),450)] or ['확인 필요']
            for n,piece in enumerate(pieces):
                h=max(50,lines(piece,700,16)*20+16)
                if current and height+h>330:
                    chunks.append(current);current=[];height=0
                current.append((label+(' (계속)' if n else ''),piece,h));height+=h
        if current:chunks.append(current)
        for index,chunk in enumerate(chunks,1):
            slide=prs.slides.add_slide(prs.slide_layouts[6])
            text(slide,30,22,900,36,f'환류과제 {record[0]} · 이행방안 검토안',26,True,'17324D')
            text(slide,30,65,900,66,title,14,color='53647A')
            y=145
            for label,value,height in chunk:
                text(slide,30,y,180,height,label,14,True,'24466A')
                text(slide,225,y,705,height,value,16)
                y+=height
            text(slide,30,502,900,22,f'KOICA v2.2 표준양식 5-4 항목 기반 | 과제 {record[0]} / {index}–{len(chunks)} | 합의·면담 여부는 별도 확인',10,color='53647A')
            slide.notes_slide.notes_text_frame.text='\n'.join(f'{h}: {v}' for h,v in zip(FEEDBACK_HEADERS,record))
    out=BytesIO();prs.save(out);return out.getvalue()
