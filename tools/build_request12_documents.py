"""Updated operator/user guide and evidence-based acceptance report."""
import argparse, ast, json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/review-20260920';OUT.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Korean','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('KoreanBold','C:/Windows/Fonts/malgunbd.ttf'))
styles={
 'title':ParagraphStyle('title',fontName='KoreanBold',fontSize=23,leading=32,textColor=HexColor('#193D5B'),spaceAfter=17,wordWrap='CJK'),
 'head':ParagraphStyle('head',fontName='KoreanBold',fontSize=14,leading=22,textColor=HexColor('#193D5B'),spaceBefore=13,spaceAfter=7,wordWrap='CJK'),
 'body':ParagraphStyle('body',fontName='Korean',fontSize=10.5,leading=17.5,spaceAfter=9,wordWrap='CJK'),
}

def build(name,pages):
    story=[];md=[]
    for i,(title,sections) in enumerate(pages):
        if i:story.append(PageBreak())
        story.append(Paragraph(escape(title),styles['title']));md.append('# '+title)
        for heading,body in sections:
            story.extend([Paragraph(escape(heading),styles['head']),Paragraph(escape(body),styles['body'])])
            md.extend(['\n## '+heading,body])
    def footer(c,doc):
        c.setStrokeColor(HexColor('#CAD7E1'));c.line(48,44,547,44)
        c.setFont('Korean',8);c.setFillColor(HexColor('#536675'))
        c.drawString(48,30,'K-ODAME 개발 서비스 | 2026.09.20');c.drawRightString(547,30,str(doc.page))
    path=OUT/(name+'.pdf')
    SimpleDocTemplate(str(path),pagesize=(595.28,841.89),leftMargin=48,rightMargin=48,topMargin=48,bottomMargin=62,title=pages[0][0],author='K-ODAME').build(story,onFirstPage=footer,onLaterPages=footer)
    (OUT/(name+'.md')).write_text('\n\n'.join(md),encoding='utf-8')
    return path

parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['manual','report']);args=parser.parse_args()
if args.kind=='manual':
    tree=ast.parse((ROOT/'tools/build_review_documents.py').read_text(encoding='utf-8'))
    pages=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='manual' for t in node.targets))
    replacements={
      '2026.09.16 개정판':('2026.09.20 개정판','개발 서비스의 관리자·사용자 흐름, 보고서 중단 후 이어쓰기, KOICA v2.2 지침 및 별도 제출 파일 기능을 반영했습니다. 서비스 버전과 KOICA 지침 버전은 별개입니다.'),
      '48%에서 멈춘 경우':('중단 후 이어서 생성','이전 사례의 48%는 13/27개 섹션에서 API 재시작으로 중단된 상태였습니다. 생성 이력을 펼쳐 남은 섹션 이어서 생성을 누릅니다. 같은 자료·평가의 성공한 섹션을 보존하고 미완료·실패 부분을 다시 작성합니다. 자료나 평가가 바뀌면 이어쓰기가 제한되므로 최신 자료로 새로 작성합니다. 복구 정보가 없는 과거 작업은 개별 섹션 생성 또는 새 작성을 사용합니다.'),
      '증빙 업로드':('증빙 업로드','자료 업로드에서 현재 사업 자료를 등록하고 파일별 접수·중복·거절 안내를 확인합니다. 처리 실패 파일은 원인을 확인한 뒤 다시 처리를 누릅니다. 더 보기를 눌러 전체 목록을 확인합니다. 처리 중인 자료가 있으면 평가·보고서 시작이 제한됩니다.'),
      'DAC 재평가':('DAC 재평가','전체 문서 재평가는 제공된 v1.4 기준의 11개 질문·55개 증빙 항목을 검토합니다. AI가 사실과 근거를 추출하고 서버의 버전 고정 규칙이 점수를 계산합니다. 질문은 1~4점, 기준 평균은 소수점 한 자리로 표시합니다. 자료 부족·충돌은 판정보류이며, 근거를 보완한 뒤 다시 평가합니다.'),
    }
    pages=[(title, [replacements.get(h,(h,b)) for h,b in sections]) for title,sections in pages]
    pages.insert(5,('05 별도 제출 서류',[
       ('등급결과표 5-2','보고서 화면의 별도 제출 서류에서 Excel 또는 한글(HWPX)을 선택해 내려받습니다. 최신 평가의 질문별 점수와 평균·총점·등급을 반영합니다. 미확인 점수는 판정보류이며 0점으로 바뀌지 않습니다. 엑셀의 판정 근거 탭에서 질문별 증빙과 한계를 확인합니다. 사후평가용 탭은 미작성 참고 양식입니다.'),
       ('교훈 리포트 5-3','PPT 또는 한글(HWPX)을 선택합니다. 저장된 교훈과 체크리스트를 본 보고서와 별도로 제출할 수 있습니다. PPT는 제공된 분야별 교훈 양식을 사용하며 원문의 사업 예시를 현재 사실로 사용하지 않습니다.'),
       ('환류과제 이행방안 5-4','Excel 또는 PPT를 선택합니다. 제공된 양식의 과제·이행주체·시기·차별성·영향·위험·면담·의견 항목을 보존합니다. 원본 Excel의 매크로는 실행하지 않으며 출력 파일은 XLSX입니다. PPT는 동일 항목을 읽기 쉽게 나눈 발표용 형식입니다.'),
       ('제출 전 확인','다운로드는 최신 자료와 평가가 반영된 보고서가 있을 때 가능합니다. 제안된 일정·담당부서, 면담 실시 여부, 의견 수용, 평가자 정보와 최종 쪽수는 사람이 확인합니다. 자료에 없는 합의나 완료 사실을 자동으로 채우지 않습니다.')]))
    pages[-1]=(pages[-1][0].replace('05','06'),pages[-1][1])
    pages[4][1].append(('PPT 생성 재시도','완료된 장표를 3장 단위로 저장합니다. 같은 보고서·모델·사진으로 다시 생성하면 저장된 장표를 이어서 사용합니다. 자료가 바뀌면 새로 생성합니다. 결제 한도로 실패하면 충전 후 재시도합니다.'))
    path=build('K-ODAME-User-Manual-20260920',pages)
    (ROOT/'samples/user-guide-current.pdf').write_bytes(path.read_bytes())
else:
    status=json.loads((ROOT/'tmp/request12-20260919/final-status.json').read_text(encoding='utf-8'))
    pages=[('12개 요청사항 검토 결과',[
        ('검토 범위','개발 서버의 관리자·사용자 기능, user01의 52개 업로드 문서와 실제 평가·보고서·다운로드 결과를 검토했습니다. 운영 서비스는 변경하지 않았습니다.'),
        ('공식 자료','사용자가 공유한 KOICA v2.2 길라잡이·표준양식·평가환류 매뉴얼과 v1.4 증빙체크 기준을 작업폴더에 보관하고 대조했습니다. 샘플의 고유 사실과 현재 사업 사실을 구별합니다.'),
        ('종합 검증',status['validation']),
        ('인계 대기','교체 PDM은 아직 제공되지 않았습니다. 계정 전달은 수신자와 전달 채널이 지정되지 않아 실행하지 않았습니다. 기존 user01 계정은 유지했으며 비밀번호를 이 보고서에 넣지 않았습니다.')])]
    for start in range(0,12,4):
        pages.append((f'요청사항 {start+1}~{min(12,start+4)}',[(f"{row['id']}. {row['item']} · {row['status']}",row['evidence']) for row in status['items'][start:start+4]]))
    pages.append(('검증 범위와 인계',[(k,v) for k,v in status['handoff'].items()]))
    path=build('K-ODAME-Review-Report-20260920',pages)
print(path)
