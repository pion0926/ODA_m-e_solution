/* Score explanations are stored evaluation output, never reconstructed from prose. */
(function (root) {
  'use strict';
  const statusLabels = {met:'충족',partial:'일부 충족',not_met:'미충족',unverified:'미확인'};
  function render(question, esc) {
    const trace = question.scoring_trace;
    const levels = trace?.levels || question.levels || {};
    const anchors = Object.entries(levels).map(([score, text]) => `<li class="${Number(score) === question.score ? 'selected' : ''}"><b>${esc(score)}점</b><span>${esc(text)}</span></li>`).join('');
    const table = anchors ? `<details class="dac-score-levels"><summary>질문별 1~4점 내부 기준</summary><ol>${anchors}</ol></details>` : '';
    if (!trace) return `<section class="dac-score-trace"><b>기준 적용 내역</b><p>이전 평가 결과입니다. 새 내부 기준의 적용 내역은 재평가 후 확인할 수 있습니다.</p>${table}</section>`;
    return `<section class="dac-score-trace" aria-label="점수 산정 기준 및 적용 내역"><div class="dac-score-title"><b>${esc(trace.selected_score)}점 산정 이유</b><span class="tag ${trace.status === 'provisional' ? 'w' : 'i'}">${trace.status === 'provisional' ? '미확인 항목 포함 · 잠정 판단' : '기준 적용 완료'}</span></div><p>${esc(trace.selected_level_reason)}</p><ul class="dac-score-checks">${(trace.checks || []).map(check => `<li><div><b>${esc(check.criterion)}</b><span class="tag ${check.status === 'met' ? 'g' : 'w'}">${esc(statusLabels[check.status] || check.status)}</span></div><p>${esc(check.finding)}</p></li>`).join('')}</ul><p class="dac-score-gap"><b>${trace.selected_score === 4 ? '유지·후속 검증 과제' : '상위 점수를 부여하지 않은 이유'}</b><br>${esc(trace.next_level_gap)}</p>${table}<small>${esc(trace.label)} · ${esc(trace.version)} · 공식 점수표가 아닌 내부 운영 기준</small></section>`;
  }
  root.DacScoringUI = {render};
})(window);
