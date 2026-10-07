/* Score explanations are stored evaluation output, never reconstructed from prose. */
(function (root) {
  'use strict';
  const statusLabels = {met:'충족',partial:'일부 충족',not_met:'미충족',unverified:'미확인'};
  function render(question, esc) {
    const trace = question.scoring_trace;
    if (trace?.rubric_digest) return renderRules(question, esc);
    const levels = trace?.levels || question.levels || {};
    const anchors = Object.entries(levels).map(([score, text]) => `<li class="${Number(score) === question.score ? 'selected' : ''}"><b>${esc(score)}점</b><span>${esc(text)}</span></li>`).join('');
    const table = anchors ? `<details class="dac-score-levels"><summary>질문별 1~4점 내부 기준</summary><ol>${anchors}</ol></details>` : '';
    if (!trace) return `<section class="dac-score-trace"><b>기준 적용 내역</b><p>이전 평가 결과입니다. 새 내부 기준의 적용 내역은 재평가 후 확인할 수 있습니다.</p>${table}</section>`;
    return `<section class="dac-score-trace" aria-label="점수 산정 기준 및 적용 내역"><div class="dac-score-title"><b>${esc(trace.selected_score)}점 산정 이유</b><span class="tag ${trace.status === 'provisional' ? 'w' : 'i'}">${trace.status === 'provisional' ? '미확인 항목 포함 · 잠정 판단' : '기준 적용 완료'}</span></div><p>${esc(trace.selected_level_reason)}</p><ul class="dac-score-checks">${(trace.checks || []).map(check => `<li><div><b>${esc(check.criterion)}</b><span class="tag ${check.status === 'met' ? 'g' : 'w'}">${esc(statusLabels[check.status] || check.status)}</span></div><p>${esc(check.finding)}</p></li>`).join('')}</ul><p class="dac-score-gap"><b>${trace.selected_score === 4 ? '유지·후속 검증 과제' : '상위 점수를 부여하지 않은 이유'}</b><br>${esc(trace.next_level_gap)}</p>${table}<small>${esc(trace.label)} · ${esc(trace.version)} · 공식 점수표가 아닌 내부 운영 기준</small></section>`;
  }
  function renderRules(question, esc) {
    const t = question.scoring_trace;
    const states = {negative:'미충족 확인',limited:'초기·일부 실행',substantial:'상당 부분',verified:'완전 충족',unverified:'미확인',conflicted:'근거 충돌',not_due:'목표시점 미도래 · 평가 제외'};
    const statuses = {proposed:'근거 기반 추천',needs_evidence:'자료보완 · 점수 보류',needs_review:'검토 필요 · 점수 보류',conflicted:'근거 충돌 · 점수 보류'};
    const quoteMap = new Map((question.evidence_quotes || []).map(e => [e.evidence_id,e]));
    const tableRows = (question.table_row_reviews || []).length ? `<details><summary>목표·실적 표 전체 행 검토 ${question.table_row_reviews.length}건</summary><ul>${question.table_row_reviews.map(r => `<li><b>${esc(r.metric)}</b> · ${r.decision === 'included' ? '정량 검토에 포함' : '해당 질문에서 제외'}<p>${esc(r.reason)}</p><small>${esc(r.file_name)} · ${esc(r.row)}행</small></li>`).join('')}</ul></details>` : '';
    const checks = (t.checks || []).map(c => {
      const files = [...new Set((c.evidence_ids || []).map(id => quoteMap.get(id)?.file_name).filter(Boolean))];
      const measurementItems = (c.measurements || []).map(m => `<p><b>${esc(m.metric)}</b> · ${esc(m.period)} · ${esc(m.population)}<br>${m.validation_error ? '원문 확인 전 제안값: ' : ''}목표 ${esc(m.target)}${esc(m.unit)} / 실적 ${esc(m.actual)}${esc(m.unit)} · ${m.validation_error ? `원문 수치 검증 실패 · 점수 반영 제외<br>${esc(m.validation_error)}` : m.ratio == null ? (m.comparable === false ? '정의·기간·대상 비교 보류' : '목표시점 미도래·불명 · 비율 평가 보류') : `평가 반영 비율 ${Math.round(m.ratio*1000)/10}%`}</p>`).join('');
      const measurements = measurementItems ? `<details><summary>정량 비교 ${(c.measurements || []).length}건 · 비율 반영 ${(c.measurements || []).filter(m => m.ratio != null).length}건</summary>${measurementItems}</details>` : '';
      return `<li><div><b>${esc(c.criterion)}</b><span class="tag ${c.state === 'verified' ? 'g' : 'w'}">${esc(states[c.state] || c.state)}</span></div><p>${esc(c.finding)}</p><small>가중치 ${esc(c.weight)}% · 성과값 ${c.merit == null ? '미판정' : esc(c.merit)} · 증거품질 ${Math.round((c.dq || 0)*100)}%</small>${(c.applied_rules || []).map(rule => `<p><b>적용 규칙:</b> ${esc(rule)}</p>`).join('')}${measurements}<details><summary>이 항목의 출처·증거품질</summary><p>출처등급 ${esc(c.quality?.effective_source_grade ?? '—')} · 직접성 ${esc(c.quality?.directness ?? '—')} · 시점 적합성 ${esc(c.quality?.recency ?? '—')} · 독립 교차검증 ${c.quality?.independent_corroboration ? '확인' : '미확인'}</p><p>${files.map(esc).join('<br>') || '연결된 원문 없음'}</p></details><p><b>판정에 필요한 자료:</b> ${esc(c.required_evidence)}</p></li>`;
    }).join('');
    const sources = (question.evidence_quotes || []).map(e => `<li><b>${esc(e.file_name)}</b> <small>${esc(e.locator?.section || '원문')} · 구간 ${esc(e.locator?.chunk_start ?? '')} · 줄 ${esc(e.locator?.start_line ?? '')}</small><blockquote style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(e.quote)}</blockquote><p>${esc(e.finding)}</p></li>`).join('');
    return `<section class="dac-score-trace" aria-label="점수 산정 기준 및 적용 내역"><div class="dac-score-title"><b>${t.selected_score == null ? '점수 판정 보류' : esc(t.selected_score)+'점 산정 근거'}</b><span class="tag i">${esc(statuses[t.status] || t.status)}</span></div><p>${esc(t.selected_level_reason)}</p><p>${t.assessment_basis === 'provisional_document_review' ? '현재 자료 기준 잠정 진단 · ' : ''}성과지수 ${t.merit_index ?? '—'} · 근거 확보율 ${Math.round((t.coverage || 0)*100)}% · 증거 신뢰도 ${esc(t.confidence)}%</p>${t.timing ? `<p>성과 판정 ${esc(t.timing.scored_count)}개 · 자료 미확인 ${esc(t.timing.unverified_count)}개 · 목표시점 미도래 ${esc(t.timing.not_due_count)}개</p>` : ''}<ul class="dac-score-checks">${checks}</ul>${tableRows}<details><summary>적용된 상한과 4점 필수 조건</summary><p>${esc(t.four_point_gate?.finding || '')}</p>${(t.applied_rules || []).map(r => `<p>최대 ${esc(r.maximum)}점: ${esc(r.reason)}</p>`).join('')}</details><details class="evidence-fold"><summary>검토한 원문 인용 ${question.evidence_quotes?.length || 0}건</summary><ul>${sources}</ul></details><p class="dac-score-gap"><b>추가 확인 사항</b><br>${esc(t.next_level_gap)}</p><small>${esc(t.label)} · ${esc(t.version)} · ${esc(t.notice)}</small></section>`;
  }
  function renderImprovements(criterion, esc) {
    const guide = criterion.improvement_guidance;
    if (!guide || !Array.isArray(guide.items)) return '';
    const labels = {review:'판정·비교 조건 확인',evidence:'증빙 보완',performance:'성과 개선'};
    const items = guide.items;
    const groups = Object.entries(labels).map(([kind,label]) => {
      const group = items.filter(item => item.kind === kind);
      if (!group.length) return '';
      return `<details class="dac-tip-group"><summary>${label} ${group.length}건</summary><ul>${group.map(item => `<li><b>${esc(item.title)}</b>${item.question ? `<p class="meta2">${esc(item.question)}</p>` : ''}<p><strong>현재 판단:</strong> ${esc(item.reason)}</p><p><strong>다음 조치:</strong> ${esc(item.action)}</p>${item.required_evidence ? `<p><strong>필요한 자료:</strong> ${esc(item.required_evidence)}</p>` : ''}</li>`).join('')}</ul></details>`;
    }).join('');
    return `<section class="dac-improvements" aria-label="${esc(criterion.name)} 평가점수 개선 팁"><h3>평가점수 개선 팁</h3>${guide.is_stale ? '<p class="dac-tip-stale" role="status">자료 또는 매핑이 변경되었습니다. 아래 안내는 이전 평가 기준이며, 보완 자료를 연결한 후 재평가해 최신 판단을 확인하세요.</p>' : ''}<p>${esc(guide.notice)}</p>${groups || '<p>저장된 세부 기준에서 추가 보완 항목이 확인되지 않았습니다. 검증된 성과와 증빙을 유지하고 후속 측정을 진행하세요.</p>'}<div class="dac-tip-actions"><a class="btn" href="#/evidence">자료 등록·연결 확인</a><a class="btn" href="#/eval/board">DAC 평가 계획 확인</a></div></section>`;
  }
  root.DacScoringUI = {render, renderImprovements};
})(window);
