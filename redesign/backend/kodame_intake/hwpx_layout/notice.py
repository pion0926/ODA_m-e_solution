"""Flow notice footnotes as paragraphs, avoiding nested one-cell layout boxes."""
from copy import deepcopy
from lxml import etree as E

HP='http://www.hancom.co.kr/hwpml/2011/paragraph'
Q=lambda name:'{'+HP+'}'+name


def repair_notice_boxes(xml):
    root=E.fromstring(xml.encode());count=0
    for table in list(root.iter(Q('tbl'))):
        if any(True for _ in table.iterdescendants(Q('tbl'))):continue
        text=''.join(table.itertext())
        if not any(token in text for token in ('본 보고서는 등록된','본 연구보고서의 내용은')):continue
        cells=list(table.iter(Q('tc')))
        if len(cells)!=1:continue
        run=table.getparent();host=run.getparent()
        if run.tag!=Q('run') or host.tag!=Q('p'):continue
        parent=host.getparent()
        if parent.tag!=Q('subList'):continue
        # Preserve a future template's authored siblings instead of deleting
        # anything outside the single note box.
        outside=deepcopy(host)
        for child in list(outside.iter(Q('tbl'))):child.getparent().remove(child)
        if ''.join(outside.itertext()).strip():continue
        paragraphs=cells[0].find(Q('subList')).findall(Q('p'))
        index=parent.index(host)
        for offset,original in enumerate(paragraphs):
            paragraph=deepcopy(original);paragraph.set('paraPrIDRef','3')
            for child in list(paragraph.iter(Q('ctrl')))+list(paragraph.iter(Q('linesegarray'))):child.getparent().remove(child)
            for child in paragraph.iter(Q('run')):child.set('charPrIDRef','85')
            parent.insert(index+offset,paragraph)
        parent.remove(host);count+=1
    return (E.tostring(root,encoding='unicode') if count else xml),count
