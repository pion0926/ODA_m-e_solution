"""TOC rows with a fixed number cell, independent of inline-tab rendering."""
from io import BytesIO
from html import escape
import binascii
import re
import unicodedata
import zipfile

from backend.oda_me.hwpx.patchers import TOC_SECTION2_LABELS, _toc_labeled_numeric_target
from backend.oda_me.hwpx.toc_registry import TOC_CHAPTER_KEYS

MARKER = 'toc_number_'


def _append_definition(header, container, tag, source_id, transform):
    existing = re.findall(rf'<hh:{tag}\b[^>]*\bid="(\d+)"', header)
    new_id = str(max(map(int, existing)) + 1)
    original = re.search(rf'<hh:{tag}\b(?=[^>]*\bid="{source_id}")[^>]*>.*?</hh:{tag}>', header, re.S)
    if original is None:
        raise ValueError(f'Missing TOC style {tag}/{source_id}')
    definition = re.sub(r'\bid="\d+"', f'id="{new_id}"', original.group(), count=1)
    definition = transform(definition)
    header = header.replace(f'</hh:{container}>', definition + f'</hh:{container}>', 1)
    header = re.sub(rf'(<hh:{container}\b[^>]*\bitemCnt=")(\d+)(")',
                    lambda m:m[1]+str(int(m[2])+1)+m[3], header, count=1)
    return header, new_id


def fixed_toc_columns(data: bytes, section_path: str = 'Contents/section1.xml') -> tuple[bytes, int]:
    """Convert each numbered row once; keep label and number editable.

    Each row remains inside its original hp:p, so the existing label-based
    page-number updater still resolves the correct number even after paging.
    The three cells are borderless: label / dot leader / right-aligned number.
    Original outer line-segment positions are preserved for text-box layout.
    """
    with zipfile.ZipFile(BytesIO(data)) as z:
        entries = {n:z.read(n) for n in z.namelist()}
        infos = z.infolist()
    xml = entries[section_path].decode('utf-8')
    xml = xml.replace('1. 평가매트릭스(Evaluation Matrix)', '2. 평가매트릭스(Evaluation Matrix)')
    targets = [(k, label, _toc_labeled_numeric_target(xml, label)) for k,label in TOC_SECTION2_LABELS.items()]
    # Never replace a containing text-box paragraph when an unfilled row has
    # no numeric target of its own; that would erase neighbouring TOC rows.
    targets = [(k,l,t) for k,l,t in targets if t is not None and MARKER not in t[2] and len(re.findall(r'<hp:p\b',t[2])) == 1]
    if not targets:
        return data, 0
    header = entries['Contents/header.xml'].decode('utf-8')

    def paragraph_style(s, alignment):
        s = re.sub(r'\btabPrIDRef="\d+"', 'tabPrIDRef="0"', s)
        s = re.sub(r'\bhorizontal="[^"]+"', f'horizontal="{alignment}"', s)
        s = re.sub(r'(<hc:(?:intent|left|right|prev|next)\b[^>]*value=")[^"]+', r'\g<1>0', s)
        s = re.sub(r'(<hh:lineSpacing\b[^>]*value=")[^"]+', r'\g<1>100', s)
        s = re.sub(r'\b(?:keepWithNext|keepLines|pageBreakBefore)="1"', lambda m:m[0].replace('"1"','"0"'), s)
        return s
    styles = {}
    for alignment in ('LEFT','DISTRIBUTE','RIGHT'):
        header, styles[alignment] = _append_definition(header,'paraProperties','paraPr','53',lambda s,a=alignment:paragraph_style(s,a))
    def leader_style(s):
        s = re.sub(r'\bheight="\d+"', 'height="700"', s, count=1)
        s = re.sub(r'\btextColor="[^"]+"', 'textColor="#000000"', s)
        return s
    header, dots_style = _append_definition(header,'charProperties','charPr','80',leader_style)

    for key,label,target in sorted(targets,key=lambda x:x[2][0],reverse=True):
        start,end,p,number_match = target
        number = number_match[2].strip()
        opening = re.match(r'<hp:p\b[^>]*>',p).group()
        chapter = key in TOC_CHAPTER_KEYS
        # Common physical right edge: 20pt indent + 413.44pt for normal rows;
        # chapter rows start at 0pt and therefore use the full 433.44pt.
        width = 43344 if chapter else 41344
        title = label.strip()
        units = sum(1 if unicodedata.east_asian_width(c) in ('W','F') else .55 for c in title)
        title_width = min(width-6500, max(6000, int(units*1100)+900))
        widths = [title_width, width-title_width-2200, 2200]
        uid = 2200000000 + binascii.crc32(key.encode()) % 1000000000
        def cell(col,text,style,char_style,name):
            return (f'<hp:tc name="{name}" header="0" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
                    '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                    f'<hp:p id="{uid+col+1}" paraPrIDRef="{style}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                    f'<hp:run charPrIDRef="{char_style}"><hp:t>{escape(text)}</hp:t></hp:run></hp:p></hp:subList>'
                    f'<hp:cellAddr colAddr="{col}" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
                    f'<hp:cellSz width="{widths[col]}" height="1100"/><hp:cellMargin left="0" right="0" top="0" bottom="0"/></hp:tc>')
        table = (f'<hp:tbl id="{uid}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="NONE" repeatHeader="0" rowCnt="1" colCnt="3" cellSpacing="0" borderFillIDRef="1" noAdjust="0">'
                 f'<hp:sz width="{width}" widthRelTo="ABSOLUTE" height="1100" heightRelTo="ABSOLUTE" protect="0"/>'
                 '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                 '<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="0" right="0" top="0" bottom="0"/><hp:tr>'
                 +cell(0,title,styles['LEFT'],'18' if chapter else '80','toc_label_'+key)
                 +cell(1,'.'*max(2,int(widths[1]/250)),styles['DISTRIBUTE'],dots_style,'toc_leader_'+key)
                 +cell(2,number,styles['RIGHT'],'61',MARKER+key)
                 +'</hp:tr></hp:tbl>')
        cache = ''.join(re.findall(r'<hp:linesegarray\b[^>]*>.*?</hp:linesegarray>',p,re.S))
        rendered = opening + '<hp:run charPrIDRef="80">'+table+'</hp:run>'+cache+'</hp:p>'
        if key == 'grade_page':
            # Native and web renderers disagree on before-spacing for an
            # inline table. Reserve two real lines below the floating ribbon.
            # This happens only on first conversion; subsequent patches are
            # numeric-cell edits and cannot accumulate spacer paragraphs.
            spacer = '<hp:p id="{id}" paraPrIDRef="40" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="18"><hp:t/></hp:run></hp:p>'
            rendered = spacer.format(id=uid+4) + spacer.format(id=uid+5) + rendered
        xml = xml[:start]+rendered+xml[end:]
    entries['Contents/header.xml'] = header.encode()
    entries[section_path] = xml.encode()
    out = BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for info in infos:z.writestr(info,entries[info.filename])
    return out.getvalue(), len(targets)
