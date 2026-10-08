"""Read actual SVG glyph/cell bounds; text presence alone cannot prove visibility."""

GEOMETRY_VERSION = 'rhwp-visible-geometry-v1'
PAGE_LABEL_VERSION = 'rhwp-printed-page-label-v1'

# Executed in the isolated offline renderer after its fonts are loaded. getBBox
# ignores clipping, which is intentional: compare the full glyph to its viewport
# and cell rectangle instead of accepting silently clipped textContent.
SVG_GEOMETRY_SCRIPT = r"""svg => {
  const parsed = new DOMParser().parseFromString(svg, 'image/svg+xml');
  if (parsed.querySelector('parsererror')) throw Error('Invalid SVG geometry');
  const root = document.importNode(parsed.documentElement, true);
  root.style.cssText = 'position:fixed;left:-20000px;top:0;pointer-events:none';
  document.body.appendChild(root);
  try {
    const vb = root.viewBox.baseVal;
    if (!(vb.width > 0 && vb.height > 0)) throw Error('Missing SVG page bounds');
    const page = {x:vb.x,y:vb.y,width:vb.width,height:vb.height};
    const inverse = root.getScreenCTM().inverse();
    const bounds = (node, box = node.getBBox(), owner = node) => {
      const matrix = inverse.multiply(owner.getScreenCTM());
      const points = [[box.x,box.y],[box.x+box.width,box.y],
        [box.x,box.y+box.height],[box.x+box.width,box.y+box.height]]
        .map(([x,y]) => new DOMPoint(x,y).matrixTransform(matrix));
      const xs=points.map(p=>p.x),ys=points.map(p=>p.y);
      return {x:Math.min(...xs),y:Math.min(...ys),
        width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)};
    };
    const exceeds = (b, outer) => b.x < outer.x-2 || b.y < outer.y-2 ||
      b.x+b.width > outer.x+outer.width+2 || b.y+b.height > outer.y+outer.height+2;
    const visible = node => {
      if (!node.textContent.trim()) return false;
      for (let n=node;n && n!==root;n=n.parentElement) {
        const style=getComputedStyle(n);
        if (style.display==='none' || style.visibility==='hidden' || style.visibility==='collapse' || Number(style.opacity)===0 ||
            Number(style.fillOpacity)===0 || style.fill==='none') return false;
      }
      return true;
    };
    const texts = [...root.querySelectorAll('text')].filter(visible).map(node => {
      const owner=node.closest('[clip-path]');
      const match=owner?.getAttribute('clip-path')?.match(/^url\(#(cell-clip-[\w-]+)\)$/);
      return {node,box:bounds(node),owner,clipId:match?.[1]};
    });
    // A plain centred page number outside all cells identifies the footer.
    // Never classify normal headers/footers as body overflow simply by margin.
    const footers=texts.filter(t => !t.owner && /^\d{1,3}$/.test(t.node.textContent.trim()) &&
      t.box.y > page.y+page.height*.9 && t.box.x > page.x+page.width*.35 &&
      t.box.x+t.box.width < page.x+page.width*.65);
    const footerTop=footers.length ? Math.min(...footers.map(t=>t.box.y)) : null;
    // Printed numbering can restart after the cover or at a section. Read
    // the actual centred footer, including split digit glyphs, rather than
    // assuming its value equals the physical page index or a fixed offset.
    const footerLines=[];
    for (const t of texts.filter(t => !t.owner &&
      t.box.y > page.y+page.height*.9 && t.box.x > page.x+page.width*.3 &&
      t.box.x+t.box.width < page.x+page.width*.7)) {
      const first=t.node.getStartPositionOfChar(0);
      const baseline=new DOMPoint(first.x,first.y)
        .matrixTransform(inverse.multiply(t.node.getScreenCTM())).y;
      let line=footerLines.find(line=>Math.abs(line.y-baseline)<1);
      if (!line) {line={y:baseline,nodes:[]};footerLines.push(line);}
      line.nodes.push(t);
    }
    const pageLabels=footerLines.map(line=>line.nodes.sort((a,b)=>a.box.x-b.box.x)
      .map(t=>t.node.textContent).join('').replace(/\s+/g,''))
      .map(text=>text.match(/^[-–—](\d{1,4})[-–—]$/)?.[1])
      .filter(Boolean);
    const errors=[],seen=new Set(),cells=new Map();
    let violationCount=0;
    const add=(kind,identity,box) => {
      const key=kind+':'+identity;
      if (seen.has(key)) return;
      seen.add(key);violationCount++;
      if(errors.length<20) errors.push({kind,cell_id:identity,box});
    };
    for (const [index,t] of texts.entries()) {
      if (exceeds(t.box,page)) add('text_outside_page',t.clipId||'text-'+index,t.box);
      if (!t.clipId) continue;
      let cell=cells.get(t.clipId);
      if (!cell) {
        const clip=root.querySelector('#'+CSS.escape(t.clipId));
        const rect=clip?.querySelector('rect');
        if (!rect || clip.getAttribute('clipPathUnits')==='objectBoundingBox' ||
            clip.hasAttribute('transform') || rect.hasAttribute('transform')) {
          add('unsupported_cell_clip',t.clipId,t.box);continue;
        }
        const b={x:Number(rect.getAttribute('x')||0),y:Number(rect.getAttribute('y')||0),
          width:Number(rect.getAttribute('width')),height:Number(rect.getAttribute('height'))};
        cell=bounds(rect,b,t.owner);cells.set(t.clipId,cell);
        if (exceeds(cell,page)) add('cell_outside_page',t.clipId,cell);
      }
      if (exceeds(t.box,cell)) add('text_outside_cell',t.clipId,t.box);
      if (footerTop!==null && t.box.y+t.box.height > footerTop+2)
        add('table_text_in_footer',t.clipId,t.box);
    }
    return {version:'rhwp-visible-geometry-v1',ok:violationCount===0,
      page,visible_text_count:texts.length,cell_count:cells.size,footer_detected:footerTop!==null,
      page_label_version:'rhwp-printed-page-label-v1',
      printed_page_label:pageLabels.length===1 ? pageLabels[0] : null,
      printed_page_label_candidates:pageLabels.length,
      violation_count:violationCount,errors};
  } finally { root.remove(); }
}"""


def validate_rendered_geometry(analysis):
    """Only the server's final rendered page bounds can certify no clipping."""
    pages = analysis.get('page_texts')
    total = analysis.get('page_count')
    if (type(total) is not int or not 1 <= total <= 200 or not isinstance(pages, list)
            or len(pages) != total or any(not isinstance(page, dict) for page in pages)
            or any(type(page.get('page_number')) is not int for page in pages)
            or [page['page_number'] for page in pages] != list(range(1, total + 1))):
        raise RuntimeError('rHWP 전체 페이지의 좌표 검사 순서·누락·중복을 확인해야 합니다. '
                           '검사하지 않은 쪽이 있는 보고서를 완료 처리하지 않았습니다.')
    errors = []
    for page in pages:
        geometry = page.get('geometry') or {}
        if geometry.get('version') != GEOMETRY_VERSION or geometry.get('ok') is not True:
            kinds = sorted({error.get('kind', 'unknown') for error in geometry.get('errors', [])})
            errors.append({'page_number': page.get('page_number'),
                           'kinds': kinds or ['geometry_not_verified']})
    if not pages or errors:
        details = ', '.join(f"{row['page_number']}쪽({','.join(row['kinds'])})" for row in errors[:10])
        raise RuntimeError('rHWP 본문이 용지·표 셀 경계를 벗어나거나 바닥글과 겹칩니다. '
                           '잘린 보고서를 완료 처리하지 않았습니다: '+(details or '쪽 검사 누락'))
    return {'ok': True, 'version': GEOMETRY_VERSION, 'page_count': len(pages)}
