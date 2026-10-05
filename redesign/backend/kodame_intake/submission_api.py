import base64
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Response
from .db import connection, current_project_id
from .project_lifecycle import project_lifecycle, capture_input_snapshot, snapshots_match
from .report_section_preview import build_section_preview
from .submission_exports import grade_workbook, feedback_workbook
from .submission_presentations import lesson_deck, feedback_deck

router=APIRouter(prefix='/api/v2/report/submissions',tags=['separate-submissions'])
KINDS={
    'grade-xlsx':('5-2_종료평가_등급결과표.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    'grade-hwpx':('5-2_종료평가_등급결과표.hwpx','application/hwp+zip'),
    'lessons-pptx':('5-3_분야별_평가교훈_리포트.pptx','application/vnd.openxmlformats-officedocument.presentationml.presentation'),
    'lessons-hwpx':('5-3_분야별_평가교훈_리포트.hwpx','application/hwp+zip'),
    'feedback-xlsx':('5-4_평가환류과제_이행방안.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    'feedback-pptx':('5-4_평가환류과제_이행방안.pptx','application/vnd.openxmlformats-officedocument.presentationml.presentation'),
}


@router.get('/{kind}')
def download_submission(kind:str):
    if kind not in KINDS:
        raise HTTPException(404,'지원하지 않는 제출 서식입니다.')
    with connection() as conn:
        lifecycle=project_lifecycle(conn)
        if not lifecycle['report_current']:
            raise HTTPException(409,'최신 자료로 평가·보고서 작성을 완료한 뒤 별도 제출 파일을 내려받아 주세요. '+lifecycle['message'])
        rows=conn.execute('SELECT part_id,status,content,source_document_ids FROM report_sections').fetchall()
        sections={r['part_id']:r for r in rows}
        source_contents={r['part_id']:r['content'] for r in rows}
        required={'grade-xlsx':'grade','grade-hwpx':'grade','lessons-pptx':'lessons','lessons-hwpx':'lessons','feedback-xlsx':'feedback','feedback-pptx':'feedback'}[kind]
        if sections[required]['status'] in {'failed','generating','empty'}:
            raise HTTPException(409,'해당 보고서 섹션의 오류를 해결한 뒤 다운로드해 주세요.')
        project=conn.execute('SELECT name FROM projects WHERE id=%s',(current_project_id(),)).fetchone()
        source_ids=sections[required].get('source_document_ids') or []
        references=conn.execute('SELECT id,original_name FROM evaluation_intake_documents ORDER BY original_name').fetchall()
        names=[r['original_name'] for r in references if str(r['id']) in source_ids]
    try:
        if kind=='grade-xlsx':
            from .main import latest_evaluations
            data=grade_workbook(project['name'],latest_evaluations()['criteria'])
        elif kind.endswith('hwpx'):
            data=base64.b64decode(build_section_preview(required,sections[required]['content'])['hwpx_base64'])
        elif kind=='lessons-pptx':
            data=lesson_deck(project['name'],sections['lessons']['content'],names)
        elif kind=='feedback-xlsx':
            data=feedback_workbook(project['name'],sections['feedback']['content'])
        else:
            data=feedback_deck(project['name'],sections['feedback']['content'])
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    with connection() as conn:
        unchanged=snapshots_match(lifecycle['input_snapshot'],capture_input_snapshot(conn))
        current=conn.execute('SELECT part_id,content,status FROM report_sections').fetchall()
        if not unchanged or any(r['status']=='generating' or source_contents.get(r['part_id'])!=r['content'] for r in current):
            raise HTTPException(409,'파일 구성 중 자료·평가 또는 보고서가 변경되었습니다. 작성 완료 후 다시 내려받아 주세요.')
    name,mime=KINDS[kind]
    return Response(data,media_type=mime,headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(name)}",'Cache-Control':'no-store'})
