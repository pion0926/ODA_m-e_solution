const { useEffect, useMemo, useState } = React;

function api(path, options = {}) {
  const timeoutMs = options.timeoutMs || 90000;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const { timeoutMs: _timeoutMs, ...fetchOptions } = options;
  return fetch(path, {
    headers: { "content-type": "application/json" },
    ...fetchOptions,
    signal: controller.signal,
    body: fetchOptions.body ? JSON.stringify(fetchOptions.body) : undefined,
  })
    .then(async (response) => {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : null;
      if (!response.ok) {
        throw new Error(payload?.error || `API ${path} failed with ${response.status}`);
      }
      return payload;
    })
    .catch((error) => {
      if (error.name === "AbortError") {
        throw new Error(`API ${path} timed out after ${Math.round(timeoutMs / 1000)}s`);
      }
      throw error;
    })
    .finally(() => window.clearTimeout(timer));
}

function polarPoint(cx, cy, radius, index, total) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
}

function polygonPoints(criteria, key, radius, cx, cy) {
  return criteria
    .map((item, index) => {
      const valueRadius = radius * ((item[key] || 1) / 4);
      return polarPoint(cx, cy, valueRadius, index, criteria.length).join(",");
    })
    .join(" ");
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function renderInlineMarkdown(text) {
  return String(text || "")
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      return <React.Fragment key={index}>{part}</React.Fragment>;
    });
}

function cleanEvaluationLine(line) {
  return String(line || "")
    .replace(/\*\*/g, "")
    .replace(/^[-•ㅇ]\s*평가결과\s*[:：]\s*/, "- ")
    .replace(/^평가결과\s*[:：]\s*/, "")
    .replace(/하였습니다/g, "하였음")
    .replace(/되었습니다/g, "되었음")
    .replace(/어렵습니다/g, "어려움")
    .replace(/필수적입니다/g, "필수")
    .replace(/부족합니다/g, "부족")
    .replace(/부재합니다/g, "부재")
    .replace(/불가능합니다/g, "불가능")
    .replace(/필요합니다/g, "필요")
    .replace(/있습니다/g, "있음")
    .replace(/없습니다/g, "없음")
    .replace(/합니다/g, "함")
    .replace(/됩니다/g, "됨")
    .replace(/입니다/g, "임")
    .replace(/([가-힣\]])[.。]\s*/g, "$1 ")
    .replace(/\s*[.。]\s*$/g, "")
    .trim();
}

function buildReferenceDocuments(criteria = []) {
  return criteria
    .flatMap((criterion) =>
      (criterion.uploadedDocuments || []).map((document) => ({
        ...document,
        criterionName: criterion.name,
        criterionId: criterion.id,
        referenceKey: `${criterion.id}-${document.id}`,
        downloadUrl: `/api/criteria/${criterion.id}/documents/${document.id}/download`,
      })),
    )
    .sort((a, b) => String(b.uploadedAt || "").localeCompare(String(a.uploadedAt || "")))
    .map((document, index) => ({ ...document, referenceNumber: index + 1 }));
}

function normalizeCitationText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\.[^.]+$/g, "")
    .replace(/[()[\]{}쨌,_\-~'":/\\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function citationTokens(document) {
  const evidence = normalizeCitationText(document.evidenceName);
  const file = normalizeCitationText(document.fileName);
  const tokens = [
    evidence,
    file,
    ...evidence.split(" "),
    ...file.split(" "),
  ].filter((token) => token.length >= 3 && !["및", "또는", "자료", "문서", "보고서"].includes(token));
  return [...new Set(tokens)];
}

function findCitationDocuments(line, criterionId, references = []) {
  const normalizedLine = normalizeCitationText(line);
  if (!criterionId || !normalizedLine || /^#{1,4}\s*/.test(line) || /^\d+(?:\.\d+)*\.$/.test(line)) return [];
  if (/^\[.+\]$/.test(line) || /^(예상점수|예상 점수|득점사유|증빙공백|점수)/.test(normalizedLine)) return [];
  const criterionReferences = references.filter((document) => document.criterionId === criterionId);
  const matched = criterionReferences.filter((document) =>
    citationTokens(document).some((token) => normalizedLine.includes(token)),
  );
  const source = matched.length ? matched : criterionReferences;
  return source.slice(0, 3);
}

function CitationLinks({ documents, onCitationClick }) {
  if (!documents?.length) return null;
  return (
    <sup className="citation-links" aria-label="근거 문서 각주">
      {documents.map((document) => (
        <button
          key={document.referenceKey}
          type="button"
          title={document.fileName}
          onClick={() => onCitationClick?.(document.referenceKey)}
        >
          [{document.referenceNumber}]
        </button>
      ))}
    </sup>
  );
}

function MarkdownBlock({ text, criterionId, references, onCitationClick }) {
  const lines = String(text || "")
    .replace(/\r\n?/g, "\n")
    .replace(/\s+(#{1,4}\s+)/g, "\n$1")
    .replace(/\s+(\*{0,2}\d+(?:\.\d+)+\.\s+)/g, "\n$1")
    .replace(/\s+(---+)/g, "\n$1")
    .split("\n")
    .map((line) => cleanEvaluationLine(line.trim()))
    .filter((line) => !/^[-–—]{3,}$/.test(line))
    .filter(Boolean);

  return (
    <div className="markdown-output">
      {lines.map((line, index) => {
        const normalizedLine = line.replace(/^\*\*(\d)/, "$1").replace(/\*\*(\s*[-–—])/, "$1");
        const citations = findCitationDocuments(normalizedLine, criterionId, references);
        const heading = normalizedLine.match(/^(#{1,4})\s*(.+)$/);
        if (heading) {
          const Tag = heading[1].length <= 2 ? "h3" : "h4";
          return <Tag key={index}>{renderInlineMarkdown(heading[2])}</Tag>;
        }

        const numbered = normalizedLine.match(/^(\d+(?:\.\d+)*\.)\s*(.+)$/);
        if (numbered) {
          return (
            <p className="numbered-line" key={index}>
              <strong>{numbered[1]}</strong> {renderInlineMarkdown(numbered[2])}
            </p>
          );
        }

        const bullet = normalizedLine.match(/^[-•ㅇ]\s*(.+)$/);
        if (bullet) {
          return (
            <p className="bullet-line" key={index}>
              {renderInlineMarkdown(bullet[1])}
              <CitationLinks documents={citations} onCitationClick={onCitationClick} />
            </p>
          );
        }

        return (
          <p key={index}>
            {renderInlineMarkdown(normalizedLine)}
            <CitationLinks documents={citations} onCitationClick={onCitationClick} />
          </p>
        );
      })}
    </div>
  );
}

function RadarChart({ title, description, criteria, series, onSelect }) {
  const size = 560;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 220;
  const levels = [0.25, 0.5, 0.75, 1];

  return (
    <article className="radar-card">
      <div className="chart-head">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>

      <svg className="radar-svg" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={title}>
        {levels.map((level) => (
          <polygon
            key={level}
            points={criteria.map((_, index) => polarPoint(cx, cy, radius * level, index, criteria.length).join(",")).join(" ")}
            className="radar-grid"
          />
        ))}
        {criteria.map((_, index) => {
          const [x, y] = polarPoint(cx, cy, radius, index, criteria.length);
          return <line key={index} x1={cx} y1={cy} x2={x} y2={y} className="radar-axis" />;
        })}
        {series.map((item) => (
          <polygon
            key={item.key}
            points={polygonPoints(criteria, item.key, radius, cx, cy)}
            className={`radar-area radar-area-${item.key}`}
            style={{ "--series-color": item.color }}
          />
        ))}
        {criteria.map((item, index) => {
          const [x, y] = polarPoint(cx, cy, radius + 30, index, criteria.length);
          const score = Number(item.currentScore4 || 1);
          const [dotX, dotY] = polarPoint(cx, cy, radius * (score / 4), index, criteria.length);
          return (
            <g
              key={item.id}
              className="radar-node"
              onClick={() => onSelect(item.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(item.id);
                }
              }}
              tabIndex="0"
              role="button"
              aria-label={`${item.name} 상세 보기`}
            >
              <title>{`${item.name} 상세 보기`}</title>
              <circle cx={dotX} cy={dotY} r="7" />
              <text x={x} y={y} textAnchor="middle">
                <tspan x={x} dy="0">{item.name}</tspan>
                <tspan x={x} dy="18">{formatScore(score)}점</tspan>
              </text>
            </g>
          );
        })}
      </svg>

      <div className="chart-legend">
        {series.map((item) => (
          <span key={item.key}><i style={{ background: item.color }}></i>{item.name}</span>
        ))}
      </div>
      <div className="criteria-shortcuts" aria-label="DAC 기준 상세 이동">
        {criteria.map((item) => (
          <button type="button" key={item.id} onClick={() => onSelect(item.id)}>
            <span>{item.name}</span>
            <strong>{formatScore(item.currentScore4 || 1)}/{item.targetScore4 || 4}점</strong>
          </button>
        ))}
      </div>
    </article>
  );
}

function ProgressBar({ value }) {
  const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="progress-track" aria-label={`${safeValue}%`}>
      <span style={{ width: `${safeValue}%` }} />
    </div>
  );
}

function formatScore(value) {
  const score = Number(value || 0);
  if (!Number.isFinite(score)) return "-";
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

function evidenceSlotStats(criterion) {
  const requiredNames = (criterion.evidence || []).map((item) => item.name).filter(Boolean);
  const filledNames = new Set(
    (criterion.uploadedDocuments || [])
      .map((document) => document.evidenceName)
      .filter((name) => requiredNames.includes(name)),
  );
  return {
    uploaded: filledNames.size,
    required: requiredNames.length,
    coverage: requiredNames.length ? Math.round((filledNames.size / requiredNames.length) * 100) : 0,
  };
}

function evidenceAwareEvaluationText(text, criterion) {
  const value = String(text || "");
  if (!/확인|보완|부족|필요|미흡|공백/.test(value)) return value;
  const evidenceStatus = criterion.evidenceStatus || {};
  const evidenceItems = criterion.evidence || [];
  const groups = [
    { pattern: /PDM|Project Design Matrix|사업설계/i, label: "PDM/사업설계" },
    { pattern: /ToC|Theory of Change|변화이론/i, label: "ToC/변화이론" },
    { pattern: /MoU|ROD|협의의사록|약정/i, label: "협의/약정 문서" },
    { pattern: /Baseline|기초선|베이스라인/i, label: "기초선/베이스라인" },
    { pattern: /CPS|CAS|KOICA|전략|정책/i, label: "전략/정책 문서" },
    { pattern: /Change Log|JSC|변경|조정/i, label: "변경/조정 문서" },
  ];
  const mentioned = groups.filter((group) => group.pattern.test(value));
  if (!mentioned.length) return value;
  const missing = mentioned.filter((group) => {
    const matchingItems = evidenceItems.filter((item) => group.pattern.test(item.name));
    return matchingItems.length && matchingItems.every((item) => !evidenceStatus[item.name]);
  });
  if (!missing.length) {
    return value;
  }
  return `${value}\n보완 필요 자료: ${missing.map((group) => group.label).join(", ")}`;
}

function cleanTaskText(value) {
  return String(value || "")
    .replace(/^\s*(?:[-•]|\d+(?:\.\d+)*\.?)\s*/, "")
    .replace(/^(?:보완|개선|확인 필요)\s*[:：]?\s*/, "")
    .trim();
}

function buildImprovementTasks({ criterion, evaluationResult, missingItems }) {
  const tasks = [];
  function addTask(title, detail, action = "자료 확인") {
    const cleanTitle = cleanTaskText(title);
    const cleanDetail = cleanTaskText(detail);
    if (!cleanTitle || tasks.some((item) => item.title === cleanTitle)) return;
    tasks.push({ title: cleanTitle, detail: cleanDetail, action });
  }

  (missingItems || []).forEach((item) => {
    addTask(
      `${item.name} 보완`,
      `${item.category || "필수 증빙"} 자료가 부족하므로 관련 문서 업로드가 필요합니다.`,
      "보완",
    );
  });

  (evaluationResult?.improvementNeeds || []).forEach((need) => {
    const text = cleanTaskText(need);
    if (!text) return;
    const action = /자료|문서|증빙|근거/.test(text)
      ? "자료 보완"
      : /면담|확인|검토|협의/.test(text)
        ? "추가 확인"
        : "후속 조치";
    addTask(action, text, action);
  });

  (evaluationResult?.questionAssessments || []).forEach((assessment) => {
    (assessment.actionItems || []).forEach((item) => {
      addTask(assessment.question || "평가질문", item, "보완 조치");
    });
    (assessment.evidenceGaps || []).forEach((item) => {
      addTask(`${item} 보완`, `${assessment.question || "평가질문"} 관련 근거 보완이 필요합니다.`, "자료 보완");
    });
  });

  const lines = [
    ...String(evaluationResult?.summary || "").split(/\n+/),
    ...(evaluationResult?.sections || []).flatMap((section) => [section.title, section.body]),
  ]
    .flatMap((line) => String(line || "").split(/\n+/))
    .map(cleanTaskText)
    .filter(Boolean);
  const gapLines = lines.filter((line) => /보완|부족|미흡|확인\s*필요|자료\s*공백|근거\s*공백|추가\s*확인|개선|환류/.test(line));

  gapLines.slice(0, 5).forEach((line) => {
    const compact = line.length > 150 ? `${line.slice(0, 149).trim()}...` : line;
    const action = /Change Log|JSC|변경/.test(line)
      ? "변경관리 자료 확인"
      : /SDGs|전략|CPS|정책/.test(line)
        ? "전략 정합성 확인"
        : /PDM|ToC|설계|MoU|ROD|약정/.test(line)
          ? "설계 근거 확인"
          : "자료 보완";
    addTask(action, compact, action);
  });

  if (!tasks.length && (evaluationResult?.score || criterion.currentScore4 || 1) < 4) {
    addTask(
      "보완자료 확인",
      "평가 점수가 4점 미만인 항목은 근거자료와 보완 필요사항을 확인해야 합니다.",
      "자료 보완",
    );
  }
  return tasks.slice(0, 5);
}

function DashboardInsights({ insights, activeTab, onSelect, onOpenReferences, onOpenCriteria, onOpenReportEditor }) {
  if (!insights) return null;
  function handleMonitoringClick(item) {
    if (item.criterionId) {
      onSelect(item.criterionId);
      return;
    }
    if (item.status === "gap") onOpenReferences();
    else onOpenReportEditor();
  }

  function handleActionClick(action) {
    const criterionMatch = (insights.criterionCards || []).find((item) => action.title?.includes(item.name));
    if (criterionMatch) {
      onSelect(criterionMatch.id);
      return;
    }
    if (action.type === "report") onOpenReportEditor();
    else onOpenReferences();
  }

  function handleGateClick(gate) {
    if (gate.action === "references") onOpenReferences();
    else if (gate.action === "criteria") onOpenCriteria?.();
    else onOpenReportEditor();
  }

  return (
    <div className="dashboard-insights">
      {activeTab === "progress" && (
        <>
          <section className="ops-panel">
            <article className="gate-board">
              <div className="gate-board-head">
                <div>
                  <span>제출 준비 현황</span>
                  <strong>{insights.readiness.score}%</strong>
                </div>
                <p>보고서 제출 전 필요한 증빙 확보, 자료 분류, 기준별 판단, 최종 검토 상태입니다.</p>
                <ProgressBar value={insights.readiness.score} />
              </div>
              <div className="gate-list">
                {(insights.reportGates || []).map((gate) => (
                  <button className={`gate-row ${gate.status}`} type="button" key={gate.label} onClick={() => handleGateClick(gate)}>
                    <header>
                      <div>
                        <span>{gate.statusLabel || (gate.status === "ok" ? "완료" : "보완")}</span>
                        <strong>{gate.label}</strong>
                      </div>
                      <b>{gate.value}</b>
                    </header>
                    <ProgressBar value={gate.progress || 0} />
                    <p>{gate.detail}</p>
                    <small>{gate.nextAction}</small>
                  </button>
                ))}
              </div>
            </article>
          </section>
        </>
      )}

      {activeTab === "actions" && (
        <section className="actions-panel dashboard-actions-panel">
        <div className="mini-head">
          <h3>우선 확인 사항</h3>
          <button type="button" onClick={onOpenReportEditor}>보고서 열기</button>
        </div>
        <div className="monitoring-list">
          {(insights.monitoringChecklist || []).map((item) => (
            <button className="monitoring-row" type="button" key={item.label} onClick={() => handleMonitoringClick(item)}>
              <span className={`status-chip ${item.status}`}>{item.status === "ok" ? "확인" : "필요"}</span>
              <div>
                <strong>{item.label}</strong>
                <p>{item.detail}</p>
              </div>
              <i>상세</i>
            </button>
          ))}
        </div>
        {insights.expertMemo && (
          <div className="expert-memo">
            <strong>{insights.expertMemo.headline}</strong>
            <p>{insights.expertMemo.body}</p>
          </div>
        )}
        {insights.nextActions.slice(0, 3).map((action, index) => (
          <button className="action-row" type="button" key={`${action.type}-${index}`} onClick={() => handleActionClick(action)}>
            <span>{index + 1}</span>
            <div>
              <strong>{action.title}</strong>
              <p>{action.body}</p>
            </div>
            <i>열기</i>
          </button>
        ))}
      </section>
      )}
    </div>
  );
}

function Dashboard({ data, onSelect, onProjectUpdate, onOpenReferences, onOpenReportEditor, onOpenCriteria }) {
  const [preview, setPreview] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activeDashboardTab, setActiveDashboardTab] = useState("progress");

  async function openOverview() {
    const result = await api(data.project.overviewPreviewUrl);
    setPreview(result);
    setPreviewOpen(true);
  }

  return (
    <main className="dashboard-main">
      <section className="dashboard-panel" aria-label="M&E Dashboard">
        <header className="product-header">
          <div className="product-brand" aria-label="ImpactOps AI 홈">
            <span className="brand-mark" aria-hidden="true">IO</span>
            <div>
              <strong>ImpactOps <em>AI</em></strong>
              <small>ODA Intelligence Workspace</small>
            </div>
          </div>
          <div className="product-context">
            <span className="live-indicator"><i aria-hidden="true"></i> 운영 모니터링</span>
            <span className="workspace-badge">KOICA · UNICEF</span>
            <button type="button" className="help-button" title="평가 운영 안내" aria-label="평가 운영 안내">?</button>
          </div>
        </header>
        <div className="project-bar">
          <div>
            <p>사업명</p>
            <h1>{data.project.title}</h1>
            <span>{data.project.period} / {data.project.budget}</span>
          </div>
          <div className="project-actions">
            <button className="overview-link" type="button" onClick={openOverview}>
              사업개요 보기
            </button>
            <button className="overview-link secondary" type="button" onClick={onOpenReferences}>
              자료목록
            </button>
            <button className="overview-link secondary" type="button" onClick={onOpenCriteria}>
              평가기준
            </button>
            <button className="overview-link report-link" type="button" onClick={onOpenReportEditor}>
              평가보고서 작성
            </button>
          </div>
        </div>
        <div className="panel-title">
          <div>
            <p>ODA 성과관리 프로젝트 대시보드</p>
            <h2>필수 확인 항목 · 증빙/평가/보고서 진행상황</h2>
          </div>
          <small>Updated {data.updatedAt}</small>
        </div>
        <div className="overall-strip">
          <article>
            <span>종합점수</span>
            <strong>{data.overall.score}/{data.overall.maxScore}</strong>
          </article>
          <article>
            <span>KOICA 평가등급</span>
            <strong>{data.overall.koicaGrade}</strong>
          </article>
          <article>
            <span>국무조정실 평가등급</span>
            <strong>{data.overall.governmentGrade}</strong>
          </article>
          <p>{data.overall.rule}</p>
        </div>
        <div className={`dashboard-workspace dashboard-workspace-${activeDashboardTab}`}>
          <div className="radar-layout">
            <RadarChart
              title={data.chartB.title}
              description={data.chartB.description}
              criteria={data.criteria}
              series={data.chartB.series}
              onSelect={onSelect}
            />
          </div>
          <div className="dashboard-side-panel">
            <div className="dashboard-tabs" role="tablist" aria-label="업무 패널 보기">
              {[
                { id: "progress", label: "진행상황", meta: `${data.insights.readiness.score}%` },
                { id: "actions", label: "우선 확인", meta: `${data.insights.monitoringChecklist?.filter((item) => item.status === "gap").length || 0}건` },
              ].map((tab) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeDashboardTab === tab.id}
                  className={activeDashboardTab === tab.id ? "active" : ""}
                  key={tab.id}
                  onClick={() => setActiveDashboardTab(tab.id)}
                >
                  <span>{tab.label}</span>
                  <strong>{tab.meta}</strong>
                </button>
              ))}
            </div>
            <DashboardInsights
              insights={data.insights}
              activeTab={activeDashboardTab}
              onSelect={onSelect}
              onOpenReferences={onOpenReferences}
              onOpenCriteria={onOpenCriteria}
              onOpenReportEditor={onOpenReportEditor}
            />
          </div>
        </div>
      </section>
      {previewOpen && preview && (
        <OverviewPreview
          preview={preview}
          onClose={() => setPreviewOpen(false)}
          onProjectUpdate={onProjectUpdate}
        />
      )}
    </main>
  );
}

function ReferenceListPage({ data, documents, highlightKey, onBack, onDashboardUpdate }) {
  const [batchMessage, setBatchMessage] = useState("");
  const [assignments, setAssignments] = useState({});
  const [batchProposals, setBatchProposals] = useState(data.pendingDocuments || []);
  const [sampleTemplates, setSampleTemplates] = useState([]);
  const [intakeRules, setIntakeRules] = useState(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rulesTab, setRulesTab] = useState("metadata");
  const [ruleSearch, setRuleSearch] = useState("");
  const [dragActive, setDragActive] = useState(false);
  useEffect(() => {
    if (!highlightKey) return;
    const target = document.getElementById(`reference-${highlightKey}`);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightKey, documents]);
  useEffect(() => {
    let cancelled = false;
    api("/api/samples/templates")
      .then((result) => {
        if (!cancelled) setSampleTemplates(result.templates || []);
      })
      .catch(() => {
        if (!cancelled) setSampleTemplates([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    api("/api/references/intake-rules").then(setIntakeRules).catch(() => setIntakeRules(null));
  }, []);

  function updateRuleConfig(section, index, patch) {
    setIntakeRules((current) => ({ ...current, [section]: current[section].map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) }));
  }

  async function saveRules() {
    setBatchMessage("전문가 분류 기준 저장 중..");
    const saved = await api("/api/references/intake-rules", { method: "POST", body: intakeRules });
    setIntakeRules(saved);
    setRulesOpen(false);
    setBatchMessage(`전문가 기준 v${saved.version} 저장 완료 · 다음 등록 자료부터 적용`);
  }

  const totalSize = documents.reduce((sum, document) => sum + (document.size || 0), 0);
  const unmatchedDocuments = data.unmatchedDocuments || [];
  const pendingDocuments = batchProposals.length ? batchProposals : data.pendingDocuments || [];
  const referenceSlots = (data.criteria || [])
    .filter((criterion) => criterion.id !== "impact")
    .flatMap((criterion) =>
      (criterion.evidence || []).map((evidence, index) => {
        const uploaded = (criterion.uploadedDocuments || []).find((document) => document.evidenceName === evidence.name);
        return {
          key: `${criterion.id}-${index}-${evidence.name}`,
          criterionId: criterion.id,
          criterionName: criterion.name,
          category: evidence.category || "기준별 증빙자료",
          evidenceName: evidence.name,
          document: uploaded,
          referenceKey: uploaded ? `${criterion.id}-${uploaded.id}` : "",
        };
      }),
    );
  const filledSlots = referenceSlots.filter((slot) => slot.document).length;
  const referenceGroups = (data.criteria || [])
    .filter((criterion) => criterion.id !== "impact")
    .map((criterion) => {
      const slots = referenceSlots.filter((slot) => slot.criterionId === criterion.id);
      return { ...criterion, slots, filled: slots.filter((slot) => slot.document).length };
    });

  async function uploadBatch(files) {
    const fileList = Array.from(files || []);
    if (!fileList.length) return;
    setBatchMessage(`${fileList.length}개 자료 내용을 읽는 중..`);
    const payload = await Promise.all(
      fileList.map(async (file) => ({
        fileName: file.name,
        mimeType: file.type || "application/octet-stream",
        contentBase64: await readFileAsBase64(file),
      })),
    );
    const result = await api("/api/references/batch-upload", {
      method: "POST",
      body: { files: payload },
    });
    setBatchProposals(result.proposals || []);
    onDashboardUpdate(result.dashboard);
    const autoCount = result.autoAssigned?.length || 0;
    const manualCount = result.proposals?.length || 0;
    setBatchMessage(`자동분류 ${autoCount}건 완료 · 수동 확인 ${manualCount}건${autoCount ? " · 관련 평가 갱신 완료" : ""}`);
  }

  function updateAssignment(documentId, patch) {
    setAssignments((current) => ({ ...current, [documentId]: { ...(current[documentId] || {}), ...patch } }));
  }

  async function assignDocument(document) {
    const assignment = assignments[document.id] || {};
    const criterionId = assignment.criterionId || data.criteria[0]?.id || "";
    const evidenceName = (assignment.customEvidence || assignment.evidenceName || "").trim();
    if (!criterionId || !evidenceName) {
      setBatchMessage("평가 기준과 자료 항목을 먼저 지정하세요.");
      return;
    }
    setBatchMessage(`${document.fileName} 배정 중..`);
    const result = await api(`/api/references/unmatched/${document.id}/assign`, {
      method: "POST",
      body: { criterionId, evidenceName },
    });
    onDashboardUpdate(result.dashboard);
    setBatchMessage(`${document.fileName} 배정 완료`);
  }

  function proposalAssignment(document) {
    const suggested = document.suggestedMatch || {};
    return {
      criterionId: data.criteria.some((item) => item.id === suggested.criterionId) ? suggested.criterionId : data.criteria[0]?.id || "",
      evidenceName: suggested.evidenceName || "",
      customEvidence: "",
      ...(assignments[document.id] || {}),
    };
  }

  async function confirmBatch() {
    const payload = pendingDocuments.map((document) => {
      const assignment = proposalAssignment(document);
      return {
        documentId: document.id,
        criterionId: assignment.criterionId,
        evidenceName: (assignment.customEvidence || assignment.evidenceName || "").trim(),
      };
    });
    if (payload.some((item) => !item.criterionId || !item.evidenceName)) {
      setBatchMessage("모든 문서의 평가 기준과 자료 항목을 확정해야 합니다.");
      return;
    }
    setBatchMessage("분류 확정 및 평가결과 생성 중..");
    const result = await api("/api/references/batch-confirm", {
      method: "POST",
      body: { assignments: payload },
    });
    setBatchProposals([]);
    setAssignments({});
    onDashboardUpdate(result.dashboard);
    setBatchMessage(`${result.assigned.length}건 확정 완료 · 관련 평가 항목 종합평가 갱신 완료`);
  }

  return (
    <main className="detail-main reference-main">
      <section className="reference-shell">
        <section className="reference-toolbar">
          <button className="back-button" type="button" onClick={onBack}>대시보드</button>
          <div>
            <p>증빙자료 관리</p>
            <h1>자료목록</h1>
            <span>{data.project.title}</span>
          </div>
          <div className="reference-toolbar-actions">
            <button className="rules-button" type="button" onClick={() => setRulesOpen(true)}>분석·배정 기준</button>
            <label className="batch-upload-button reference-toolbar-upload">자료 일괄등록<input type="file" multiple onChange={(event) => { uploadBatch(event.target.files); event.target.value = ""; }} /></label>
          </div>
        </section>

        <div className="reference-summary">
          <article>
            <span>자료 슬롯</span>
            <strong>{filledSlots}/{referenceSlots.length}</strong>
          </article>
          <article>
            <span>업로드 문서</span>
            <strong>{documents.length}</strong>
          </article>
          <article>
            <span>분류 대기</span>
            <strong>{pendingDocuments.length + unmatchedDocuments.length}</strong>
          </article>
          <article>
            <span>총 용량</span>
            <strong>{Math.round(totalSize / 1024).toLocaleString()} KB</strong>
          </article>
        </div>

        <section className="reference-panel">
          <div className="reference-head">
            <h2>기준별 자료 슬롯</h2>
            <p>업로드된 자료까지 포함해 DAC 기준별 필수 증빙 슬롯을 한눈에 확인합니다.</p>
          </div>

          <div
            className={`batch-upload-box batch-drop-zone ${dragActive ? "drag-active" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragActive(false); }}
            onDrop={(event) => { event.preventDefault(); setDragActive(false); uploadBatch(event.dataTransfer.files); }}
          >
            <div>
              <h3>자료 일괄등록</h3>
              <p>여러 파일을 이 영역에 끌어 놓으세요. 본문 추출 → 메타데이터 정리 → 전문가 규칙과 AI 교차분석 → 슬롯 제안 순서로 처리합니다.</p>
            </div>
            <span className="drop-zone-hint">파일을 여기에 놓기</span>
          </div>
          {batchMessage && <p className="batch-message">{batchMessage}</p>}
          {rulesOpen && intakeRules && (
            <div className="rules-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setRulesOpen(false); }}>
              <section className="rules-modal" role="dialog" aria-modal="true" aria-label="자료 분석 및 배정 기준">
                <header><div><p>EXPERT CONTROL</p><h2>자료 분석·슬롯 배정 기준</h2><span>코드 수정 없이 다음 등록부터 적용됩니다. 현재 버전 v{intakeRules.version}</span></div><button type="button" onClick={() => setRulesOpen(false)}>닫기</button></header>
                <nav>
                  <button className={rulesTab === "metadata" ? "active" : ""} type="button" onClick={() => setRulesTab("metadata")}>① 분석 메타데이터</button>
                  <button className={rulesTab === "policy" ? "active" : ""} type="button" onClick={() => setRulesTab("policy")}>② 자동배정 정책</button>
                  <button className={rulesTab === "slots" ? "active" : ""} type="button" onClick={() => setRulesTab("slots")}>③ 슬롯별 규칙</button>
                </nav>
                <div className="rules-modal-body">
                  {rulesTab === "metadata" && <><div className="rule-guide"><strong>LLM이 모든 자료에서 추출할 정형 항목</strong><span>필수 여부와 설명을 바꾸면 AI 분석 기준도 함께 바뀝니다.</span></div><div className="metadata-rule-list">{intakeRules.metadataFields.map((field, index) => <article key={field.key}><input value={field.label} aria-label="항목명" onChange={(e) => updateRuleConfig("metadataFields", index, { label: e.target.value })}/><input value={field.description} aria-label="추출 기준" onChange={(e) => updateRuleConfig("metadataFields", index, { description: e.target.value })}/><input value={field.examples || ""} aria-label="예시" onChange={(e) => updateRuleConfig("metadataFields", index, { examples: e.target.value })}/><label><input type="checkbox" checked={field.required} onChange={(e) => updateRuleConfig("metadataFields", index, { required: e.target.checked })}/> 필수</label></article>)}</div></>}
                  {rulesTab === "policy" && <div className="policy-grid"><label>자동 확정 최소 신뢰도<strong>{Math.round(intakeRules.allocationPolicy.autoAssignThreshold * 100)}%</strong><input type="range" min="0.5" max="0.98" step="0.01" value={intakeRules.allocationPolicy.autoAssignThreshold} onChange={(e) => setIntakeRules((c) => ({...c, allocationPolicy:{...c.allocationPolicy, autoAssignThreshold:Number(e.target.value)}}))}/></label><label>1·2순위 최소 점수 차<strong>{Math.round(intakeRules.allocationPolicy.minimumMargin * 100)}%p</strong><input type="range" min="0" max="0.4" step="0.01" value={intakeRules.allocationPolicy.minimumMargin} onChange={(e) => setIntakeRules((c) => ({...c, allocationPolicy:{...c.allocationPolicy, minimumMargin:Number(e.target.value)}}))}/></label><label className="policy-instructions">전문가 판단 원칙<textarea value={intakeRules.allocationPolicy.instructions} onChange={(e) => setIntakeRules((c) => ({...c, allocationPolicy:{...c.allocationPolicy, instructions:e.target.value}}))}/></label></div>}
                  {rulesTab === "slots" && <><div className="rule-guide"><div><strong>사전 정의 슬롯 {intakeRules.slotRules.length}개</strong><span>전문가가 자연어로 판단 기준을 작성하면 LLM이 문서 전체 의미와 대조합니다.</span></div><input placeholder="기준·슬롯명 검색" value={ruleSearch} onChange={(e) => setRuleSearch(e.target.value)}/></div><div className="slot-rule-list semantic-rules">{intakeRules.slotRules.map((rule, index) => ({rule,index})).filter(({rule}) => `${rule.criterionName} ${rule.evidenceName}`.includes(ruleSearch)).map(({rule,index}) => <article key={`${rule.criterionId}-${rule.evidenceName}`}><div className="slot-rule-title"><label><input type="checkbox" checked={rule.enabled} onChange={(e) => updateRuleConfig("slotRules", index, {enabled:e.target.checked})}/><strong>{rule.criterionName}</strong></label><span>{rule.evidenceName}</span><label className="priority-field">판단 우선순위<select value={rule.priority} onChange={(e) => updateRuleConfig("slotRules", index, {priority:Number(e.target.value)})}>{[1,2,3,4,5].map(v=><option key={v} value={v}>{v}</option>)}</select></label></div><label>이 슬롯에 배정하는 기준<textarea value={rule.assignmentGuidance || ""} onChange={(e) => updateRuleConfig("slotRules", index, {assignmentGuidance:e.target.value})}/></label><label>이 슬롯에 배정하지 않는 조건<textarea value={rule.rejectionGuidance || ""} onChange={(e) => updateRuleConfig("slotRules", index, {rejectionGuidance:e.target.value})}/></label><label>대표 자료 예시<input placeholder="쉼표로 구분" value={(rule.examples || []).join(", ")} onChange={(e) => updateRuleConfig("slotRules", index, {examples:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)})}/></label></article>)}</div></>}
                </div>
                <footer><span>저장 전 기존 자료에는 영향을 주지 않습니다.</span><button type="button" onClick={saveRules}>기준 저장 및 적용</button></footer>
              </section>
            </div>
          )}

          {sampleTemplates.length > 0 && (
            <section className="sample-template-box">
              <div className="sample-template-head">
                <div>
                  <h3>샘플 서식 다운로드</h3>
                  <p>종료평가 보고서, 등급표, 교훈 리포트 작성에 필요한 기본 서식을 내려받습니다.</p>
                </div>
              </div>
              <div className="sample-template-list">
                {sampleTemplates.map((item) => (
                  <a className="sample-template-card" href={item.downloadUrl} download key={item.id}>
                    <span>{item.extension}</span>
                    <strong>{item.name}</strong>
                    <small>{Math.round((item.size || 0) / 1024).toLocaleString()} KB</small>
                  </a>
                ))}
              </div>
            </section>
          )}

          {pendingDocuments.length > 0 && (
            <section className="proposal-box">
              <div className="proposal-head">
                <div>
                  <h3>분류 제안 확인</h3>
                  <p>자동분류 확신도가 낮은 자료입니다. 평가 기준과 자료 항목을 최종 확정하면 해당 평가 항목의 LLM 종합평가가 실행됩니다.</p>
                </div>
                <button type="button" onClick={confirmBatch}>분류 확정 및 평가 실행</button>
              </div>
              <div className="proposal-list">
                {pendingDocuments.map((document) => {
                  const assignment = proposalAssignment(document);
                  const criterion = data.criteria.find((item) => item.id === assignment.criterionId) || data.criteria[0];
                  return (
                    <article className="proposal-card" key={document.id}>
                      <div>
                        <strong>{document.fileName}</strong>
                        <span>
                          {document.suggestedMatch
                            ? `AI 제안: ${document.suggestedMatch.criterionName} · ${document.suggestedMatch.evidenceName} (${Math.round((document.suggestedMatch.confidence || 0) * 100)}%)`
                            : "AI 제안 없음 · 직접 지정 필요"}
                        </span>
                        {document.analysisMetadata && (
                          <details className="analysis-preview">
                            <summary>추출 메타데이터 보기</summary>
                            <dl>
                              <div><dt>자료 유형</dt><dd>{document.analysisMetadata.documentType || "-"}</dd></div>
                              <div><dt>대상 기간</dt><dd>{document.analysisMetadata.period || "-"}</dd></div>
                              <div><dt>지역</dt><dd>{document.analysisMetadata.region || "-"}</dd></div>
                              <div><dt>분석 방식</dt><dd>{document.analysisMetadata.analysisMethod || "-"}</dd></div>
                            </dl>
                            <p>{document.analysisMetadata.summary || "요약을 생성하지 못했습니다."}</p>
                          </details>
                        )}
                      </div>
                      <select
                        value={assignment.criterionId}
                        onChange={(event) => updateAssignment(document.id, { criterionId: event.target.value, evidenceName: "", customEvidence: "" })}
                      >
                        {data.criteria.filter((item) => item.id !== "impact").map((item) => (
                          <option value={item.id} key={item.id}>{item.name}</option>
                        ))}
                      </select>
                      <select
                        value={assignment.evidenceName}
                        onChange={(event) => updateAssignment(document.id, { evidenceName: event.target.value, customEvidence: "" })}
                      >
                        <option value="">자료 항목 선택</option>
                        {(criterion?.evidence || []).map((item) => (
                          <option value={item.name} key={item.name}>{item.name}</option>
                        ))}
                      </select>
                      <input
                        type="text"
                        value={assignment.customEvidence}
                        placeholder="신규 항목명 직접 입력"
                        onChange={(event) => updateAssignment(document.id, { customEvidence: event.target.value })}
                      />
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          {unmatchedDocuments.length > 0 && (
            <section className="unmatched-box">
              <h3>수동 지정 필요 문서</h3>
              <p>자동 매칭 근거를 찾지 못한 문서는 평가 기준과 자료 항목을 직접 지정하거나 신규 항목명을 입력하세요.</p>
              <div className="unmatched-list">
                {unmatchedDocuments.map((document) => {
                  const assignment = assignments[document.id] || {};
                  const criterionId = assignment.criterionId || data.criteria[0]?.id || "";
                  const criterion = data.criteria.find((item) => item.id === criterionId) || data.criteria[0];
                  return (
                    <article className="unmatched-card" key={document.id}>
                      <div>
                        <strong>{document.fileName}</strong>
                        <span>{Math.round((document.size || 0) / 1024).toLocaleString()} KB · {document.uploadedAt}</span>
                      </div>
                      <select
                        value={criterionId}
                        onChange={(event) => updateAssignment(document.id, { criterionId: event.target.value, evidenceName: "", customEvidence: "" })}
                      >
                        {data.criteria.filter((item) => item.id !== "impact").map((item) => (
                          <option value={item.id} key={item.id}>{item.name}</option>
                        ))}
                      </select>
                      <select
                        value={assignment.evidenceName || ""}
                        onChange={(event) => updateAssignment(document.id, { evidenceName: event.target.value, customEvidence: "" })}
                      >
                        <option value="">자료 항목 선택</option>
                        {(criterion?.evidence || []).map((item) => (
                          <option value={item.name} key={item.name}>{item.name}</option>
                        ))}
                      </select>
                      <input
                        type="text"
                        value={assignment.customEvidence || ""}
                        placeholder="신규 항목명 직접 입력"
                        onChange={(event) => updateAssignment(document.id, { customEvidence: event.target.value })}
                      />
                      <button type="button" onClick={() => assignDocument(document)}>배정</button>
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          <div className="reference-criteria-groups">
            {referenceGroups.map((group, groupIndex) => {
              const progress = group.slots.length ? Math.round((group.filled / group.slots.length) * 100) : 0;
              return (
                <section className={`reference-criterion-group criterion-tone-${groupIndex + 1}`} key={group.id}>
                  <header>
                    <div className="criterion-group-title">
                      <span>{String(groupIndex + 1).padStart(2, "0")}</span>
                      <div><p>OECD DAC 평가기준</p><h3>{group.name}</h3></div>
                    </div>
                    <div className="criterion-group-progress">
                      <strong>{group.filled}/{group.slots.length}</strong>
                      <span>{progress}% 확보</span>
                      <div><i style={{ width: `${progress}%` }} /></div>
                    </div>
                  </header>
                  <div className="criterion-slot-head"><span>자료 구분</span><span>필요 자료 슬롯</span><span>연결된 자료</span></div>
                  <div className="criterion-slot-list">
                    {group.slots.map((slot, slotIndex) => {
                      const document = slot.document;
                      return (
                        <article
                          id={slot.referenceKey ? `reference-${slot.referenceKey}` : undefined}
                          className={`${document ? "filled" : "empty"} ${highlightKey === slot.referenceKey ? "highlight-reference" : ""}`}
                          key={slot.key}
                        >
                          <div className="slot-category"><span>{slotIndex + 1}</span><p>{slot.category}</p></div>
                          <div className="slot-requirement"><span className={document ? "slot-state ready" : "slot-state pending"}>{document ? "확보" : "필요"}</span><strong>{slot.evidenceName}</strong></div>
                          <div className="slot-document">
                            {document ? <><div><strong>{document.fileName}</strong><small>{document.uploadedAt || "등록일 확인 중"}{document.textPath ? " · 텍스트 추출 완료" : ""}</small></div><a className="download-link" href={`/api/criteria/${slot.criterionId}/documents/${document.id}/download`} download>다운로드</a></> : <><div><strong>등록된 자료 없음</strong><small>일괄등록 또는 해당 슬롯에서 자료를 추가하세요.</small></div><span className="slot-empty-mark">대기</span></>}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </section>
      </section>
    </main>
  );
}

function OverviewPreview({ preview, onClose, onProjectUpdate }) {
  const [currentPreview, setCurrentPreview] = useState(preview);
  const [uploadMessage, setUploadMessage] = useState("");
  const [rhwpStatus, setRhwpStatus] = useState("");
  const [loadVersion, setLoadVersion] = useState(0);
  const iframeRef = React.useRef(null);
  const previewData = currentPreview;
  const file = previewData.file || {};
  const fileName = String(file.name || "사업개요서.hwp").split(/[\\/]/).filter(Boolean).pop() || "사업개요서.hwp";
  const fileExists = Boolean(file.exists && file.downloadUrl);
  const isRhwpFile = /\.(hwp|hwpx)$/i.test(fileName);
  const canOpenRhwp = fileExists && isRhwpFile;
  const sizeKb = Math.round((file.size || 0) / 1024).toLocaleString();

  useEffect(() => {
    if (!canOpenRhwp) {
      setRhwpStatus(fileExists ? "HWP/HWPX 파일을 업로드하면 rhwp 에디터에서 원본을 볼 수 있습니다." : "");
      return undefined;
    }
    const iframe = iframeRef.current;
    if (!iframe) return undefined;
    let cancelled = false;
    let bridge = null;

    async function waitForIframe() {
      if (iframe.contentDocument?.readyState === "complete") return;
      await new Promise((resolve) => iframe.addEventListener("load", resolve, { once: true }));
    }

    async function loadOverviewFile() {
      try {
        setRhwpStatus("사업개요서 원본 파일 다운로드 중..");
        const fileRequest = fetch(file.downloadUrl);
        await waitForIframe();
        if (cancelled) return;
        bridge = createRhwpBridge(iframe);
        setRhwpStatus("rhwp 에디터 초기화 중..");
        await bridge.ready();
        if (cancelled) return;
        const response = await fileRequest;
        if (!response.ok) throw new Error(`사업개요서 파일을 불러오지 못했습니다. (${response.status})`);
        const buffer = await response.arrayBuffer();
        setRhwpStatus("사업개요서 원본을 rhwp 에디터에 여는 중..");
        await bridge.loadFile(buffer, fileName);
        if (cancelled) return;
        setRhwpStatus(`사업개요서 원본 로드 완료 · ${fileName}`);
      } catch (error) {
        if (!cancelled) setRhwpStatus(error.message || "사업개요서 원본을 rhwp 에디터에 열지 못했습니다.");
      }
    }

    loadOverviewFile();
    return () => {
      cancelled = true;
      if (bridge) bridge.destroy();
    };
  }, [canOpenRhwp, fileExists, file.downloadUrl, fileName, loadVersion]);

  async function uploadOverview(file) {
    setUploadMessage("사업개요서 원본 업로드 중..");
    setRhwpStatus("");
    const contentBase64 = await readFileAsBase64(file);
    const result = await api("/api/project/overview-file", {
      method: "POST",
      body: {
        fileName: file.name,
        mimeType: file.type || "application/octet-stream",
        contentBase64,
      },
    });
    setCurrentPreview({ ...previewData, project: result.project, file: result.file });
    setLoadVersion((value) => value + 1);
    onProjectUpdate(result.project, result.dashboard);
    setUploadMessage(result.message);
  }

  return (
    <div className="preview-backdrop" role="dialog" aria-modal="true" aria-label="사업개요서 보기">
      <section className="preview-panel overview-editor-panel">
        <div className="preview-head">
          <div>
            <p>사업개요서 원본 보기</p>
            <h2>{previewData.project.title}</h2>
            <span>{fileExists ? rhwpStatus || `${previewData.project.period} / ${previewData.project.budget}` : "사업개요서 HWP/HWPX 원본을 먼저 등록하세요."}</span>
          </div>
          <button type="button" onClick={onClose} aria-label="미리보기 닫기">닫기</button>
        </div>

        {fileExists ? (
          <>
            <div className="preview-file overview-file-bar">
              <strong>{fileName}</strong>
              <dl>
                <div><dt>파일 크기</dt><dd>{sizeKb} KB</dd></div>
                <div><dt>수정일</dt><dd>{file.lastModified || "-"}</dd></div>
                <div><dt>구분</dt><dd>{file.source === "uploaded" ? "등록된 사업개요서" : "기본 예시 파일"}</dd></div>
                <div><dt>원본 형식</dt><dd>{isRhwpFile ? "rhwp 미리보기 가능" : "HWP/HWPX 아님"}</dd></div>
              </dl>
              <div className="preview-actions overview-file-actions">
                <a href={file.downloadUrl} target="_blank" rel="noreferrer">원본 다운로드</a>
                <label className="overview-upload-button">
                  사업개요서 교체 업로드
                  <input
                    type="file"
                    accept=".hwp,.hwpx"
                    onChange={(event) => {
                      const nextFile = event.target.files?.[0];
                      if (nextFile) uploadOverview(nextFile);
                    }}
                  />
                </label>
              </div>
            </div>
            {canOpenRhwp ? (
              <div className="overview-rhwp-layout">
                <div className="rhwp-frame-wrap overview-rhwp-frame">
                  <iframe
                    ref={iframeRef}
                    title="rhwp 사업개요서 원본 편집기"
                    src={`/assets/rhwp/index.html?autofix=1&overview=${loadVersion}`}
                    allow="clipboard-read; clipboard-write"
                  />
                </div>
              </div>
            ) : (
              <div className="overview-empty-state">
                <strong>rhwp 에디터에서 열 수 없는 파일 형식입니다.</strong>
                <p>사업개요서 원본을 양식 그대로 확인하려면 HWP 또는 HWPX 파일을 업로드하세요.</p>
              </div>
            )}
          </>
        ) : (
          <div className="overview-empty-state">
            <strong>사업개요서가 아직 등록되지 않았습니다.</strong>
            <p>최종 보고서의 표지, 대상사업 개요, PDM, 평가 범위 작성에 쓸 HWP/HWPX 사업개요서 원본을 먼저 업로드하세요.</p>
            <label className="overview-upload-button">
              사업개요서 원본 업로드
              <input
                type="file"
                accept=".hwp,.hwpx"
                onChange={(event) => {
                  const nextFile = event.target.files?.[0];
                  if (nextFile) uploadOverview(nextFile);
                }}
              />
            </label>
          </div>
        )}
        {uploadMessage && <p className="preview-upload-message">{uploadMessage}</p>}
      </section>
    </div>
  );
}

function EvidenceItem({ item, value, onUpload, onDelete }) {
  const itemName = typeof item === "string" ? item : item.name;
  const category = typeof item === "string" ? "" : item.category;
  const documents = value?.documents || [];
  const status = documents.length ? "available" : "none";
  return (
    <section className={`evidence-card ${status}`}>
      <div>
        {category && <span className="evidence-category">{category}</span>}
        <strong>{itemName}</strong>
        <p>{status === "available" ? "업로드 완료 · 있음" : "업로드 전 · 없음"}</p>
      </div>
      <div className="evidence-actions">
        <span className={`status-pill ${status}`}>{status === "available" ? "있음" : "없음"}</span>
        <label className="upload-button">
          업로드
          <input
            type="file"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(itemName, file);
            }}
          />
        </label>
      </div>
      {fileName && <span className="file-name">{fileName}</span>}
    </section>
  );
}

function EvidenceItemV2({ item, value, onUpload, onDelete }) {
  const itemName = typeof item === "string" ? item : item.name;
  const category = typeof item === "string" ? "" : item.category;
  const documents = value?.documents || [];
  const status = documents.length ? "available" : "none";

  return (
    <section className={`evidence-card ${status}`}>
      <div>
        {category && <span className="evidence-category">{category}</span>}
        <strong>{itemName}</strong>
        <p>{status === "available" ? `업로드 완료 · ${documents.length}개 있음` : "업로드 전 · 없음"}</p>
      </div>
      <div className="evidence-actions">
        <span className={`status-pill ${status}`}>{status === "available" ? "있음" : "없음"}</span>
        <label className="upload-button">
          {status === "available" ? "추가 업로드" : "업로드"}
          <input
            type="file"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(itemName, file);
              event.target.value = "";
            }}
          />
        </label>
      </div>
      {documents.length > 0 && (
        <div className="uploaded-doc-list">
          {documents.map((document) => (
            <div className="uploaded-doc-row" key={document.id}>
              <span className="file-name">{document.fileName}</span>
              <button type="button" onClick={() => onDelete(itemName, document.id, document.fileName)}>
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function QuestionMetaGroup({ label, items, tone = "" }) {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!values.length) return null;
  return (
    <div className={`question-meta-group ${tone}`}>
      <span>{label}</span>
      <div>
        {values.map((item, index) => (
          <b key={`${label}-${index}-${item}`}>{item}</b>
        ))}
      </div>
    </div>
  );
}

function DetailPage({ criterion, references, onBack, onDashboardUpdate, onOpenReference }) {
  const [items, setItems] = useState(() =>
    (criterion.uploadedDocuments || []).reduce((acc, document) => {
      const current = acc[document.evidenceName]?.documents || [];
      acc[document.evidenceName] = { status: "available", documents: [...current, document] };
      return acc;
    }, {}),
  );
  const [customItems, setCustomItems] = useState([]);
  const [newItem, setNewItem] = useState("");
  const [message, setMessage] = useState("");
  const [evaluationResult, setEvaluationResult] = useState(criterion.evaluationResult);
  const [uploadingName, setUploadingName] = useState("");

  const checklistItems = useMemo(
    () => [...criterion.evidence, ...customItems],
    [criterion.evidence, customItems],
  );
  const missingItems = checklistItems
    .map((entry) => (typeof entry === "string" ? { category: "", name: entry } : entry))
    .filter((entry) => !(items[entry.name]?.documents || []).length);
  const uploadedCount = checklistItems.length - missingItems.length;
  const improvementTasks = useMemo(
    () => buildImprovementTasks({ criterion, evaluationResult, missingItems }),
    [criterion, evaluationResult, missingItems],
  );
  const hasEvaluationDraft = Boolean(
    evaluationResult
      && evaluationResult.status !== "waiting"
      && (
        evaluationResult.score
        || evaluationResult.sections?.length
        || (evaluationResult.summary && !/자료 업로드|업로드된 자료를 기반|평가 필수 증빙/.test(evaluationResult.summary))
      ),
  );

  function addCustomItem() {
    const name = newItem.trim();
    const exists = checklistItems.some((item) => (typeof item === "string" ? item : item.name) === name);
    if (!name || exists) return;
    setCustomItems((current) => [...current, { category: "수동 추가 자료", name }]);
    setNewItem("");
    setItems((current) => ({ ...current, [name]: { status: "none", documents: [], custom: true } }));
  }

  async function uploadEvidence(name, file) {
    setUploadingName(name);
    setMessage(`${name} 업로드 및 텍스트 저장 중..`);
    const contentBase64 = await readFileAsBase64(file);
    const result = await api(`/api/criteria/${criterion.id}/documents`, {
      method: "POST",
      body: {
        evidenceName: name,
        fileName: file.name,
        mimeType: file.type || "application/octet-stream",
        contentBase64,
      },
    });
    setItems((current) => ({
      ...current,
      [name]: {
        status: "available",
        documents: [...(current[name]?.documents || []), result.document],
      },
    }));
    const sameCriterionShared = (result.sharedDocuments || []).filter((document) => document.criterionId === criterion.id);
    if (sameCriterionShared.length) {
      setItems((current) => {
        const next = { ...current };
        sameCriterionShared.forEach((document) => {
          const sharedName = document.evidenceName;
          next[sharedName] = {
            ...(next[sharedName] || {}),
            status: "available",
            documents: [...(next[sharedName]?.documents || []), document],
          };
        });
        return next;
      });
    }
    if (result.evaluationResult) setEvaluationResult(result.evaluationResult);
    if (result.dashboard) onDashboardUpdate(result.dashboard);
    setUploadingName("");
    const sharedCount = (result.sharedDocuments || []).length;
    setMessage(`${file.name} 업로드 완료 · ${sharedCount ? `공유 슬롯 ${sharedCount}건 반영 · ` : ""}평가 요청 처리됨`);
  }

  async function deleteEvidence(name, documentId, fileName) {
    setMessage(`${fileName} 삭제 중..`);
    const result = await api(`/api/criteria/${criterion.id}/documents/${documentId}`, { method: "DELETE" });
    setItems((current) => {
      const documents = (current[name]?.documents || []).filter((document) => document.id !== documentId);
      return {
        ...current,
        [name]: {
          ...(current[name] || {}),
          status: documents.length ? "available" : "none",
          documents,
        },
      };
    });
    if (result.evaluationResult) setEvaluationResult(result.evaluationResult);
    if (result.dashboard) onDashboardUpdate(result.dashboard);
    setMessage(`${fileName} 삭제 완료`);
  }

  async function save() {
    const payload = checklistItems.map((entry) => {
      const name = typeof entry === "string" ? entry : entry.name;
      const item = items[name] || {};
      return {
        category: typeof entry === "string" ? "" : entry.category,
        name,
        ...item,
        status: item.documents?.length ? "available" : "none",
      };
    });
    const result = await api(`/api/criteria/${criterion.id}/evidence`, { method: "POST", body: { items: payload } });
    setMessage(`${result.audit.action} - ${result.audit.checkedAt}`);
  }

  return (
    <main className="detail-shell">
      <section className="detail-panel">
        <p className="signal detail-signal"><span></span>DAC 6 Criteria Detail</p>
        <div className="detail-title">
          <button className="back-button" type="button" onClick={onBack}>대시보드</button>
          <div>
            <h1>{criterion.name}</h1>
            <p>자료 보완, 평가결과 검토, 증빙 업로드를 처리하는 작업 화면입니다. 채점 기준과 세부 루브릭은 평가기준 탭에서 확인합니다.</p>
          </div>
          <div className="detail-score">
            <strong>{formatScore(evaluationResult?.score || criterion.currentScore4)}</strong>
            <span>질문 평균 점수</span>
          </div>
        </div>

        <section className="gap-first-box">
          <div className="gap-first-head">
            <div>
              <h2>현재 보완 필요사항</h2>
              <p>평가결과 확정 전에 먼저 확인해야 할 자료와 판단 공백입니다.</p>
            </div>
            <strong>{uploadedCount}/{checklistItems.length}건 확보</strong>
          </div>
          {improvementTasks.length ? (
            <div className="gap-list">
              {improvementTasks.map((item, index) => (
                <button className="gap-row" type="button" key={`${item.action}-${item.title}`} onClick={() => setNewItem(item.title)}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                    <small>{item.action}</small>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="gap-complete">
              <strong>즉시 보완할 작업은 없습니다.</strong>
              <p>필수 증빙, 평가결과 근거, 보고서 반영 상태가 모두 정리된 상태입니다.</p>
            </div>
          )}
        </section>

        {hasEvaluationDraft && (
          <section className="definition-box evaluation-result-box">
            <div className="evaluation-result-head">
              <div>
                <h2>평가결과</h2>
                <MarkdownBlock
                  text={evaluationResult.summary}
                  criterionId={criterion.id}
                  references={references}
                  onCitationClick={onOpenReference}
                />
              </div>
              {evaluationResult.score && <span>{formatScore(evaluationResult.score)}</span>}
            </div>
            {evaluationResult.questionAssessments?.length > 0 && (
              <div className="question-score-list">
                <div className="question-score-head">
                  <strong>평가질문별 점수</strong>
                  <span>평균 {formatScore(evaluationResult.score)}</span>
                </div>
                {evaluationResult.questionAssessments.map((assessment, index) => (
                  <article key={assessment.questionId || `${assessment.question}-${index}`}>
                    <div className="question-score-mark">
                      <span>{assessment.questionId || `q${index + 1}`}</span>
                      <b>{formatScore(assessment.score)}점</b>
                    </div>
                    <div className="question-score-main">
                      <header>
                        <strong>{assessment.question}</strong>
                      </header>
                      {assessment.finding && (
                        <p className="question-finding">
                          <span>핵심 판단</span>
                          {assessment.finding}
                        </p>
                      )}
                      <div className="question-score-meta">
                        <QuestionMetaGroup label="근거 문서" items={assessment.evidenceUsed} />
                        <QuestionMetaGroup label="증빙 공백" items={assessment.evidenceGaps} tone="warning" />
                        <QuestionMetaGroup label="보완 조치" items={assessment.actionItems} tone="action" />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
            {evaluationResult.sections?.length > 0 && (
              <details className="evaluation-detail-drawer">
                <summary>본문 상세 근거 보기</summary>
                <div className="evaluation-sections">
                {evaluationResult.sections.map((section) => (
                  <article key={section.title}>
                    <h3>{section.title}</h3>
                    <MarkdownBlock
                      text={evidenceAwareEvaluationText(section.body, criterion)}
                      criterionId={criterion.id}
                      references={references}
                      onCitationClick={onOpenReference}
                    />
                  </article>
                ))}
                </div>
              </details>
            )}
          </section>
        )}

        <section className="checklist-box">
          <div className="checklist-head">
            <div>
              <h2>업로드해야 할 파일 목록</h2>
              <p>자료 업로드 전에는 없음으로 표시되고, 업로드가 완료되면 있음으로 자동 전환됩니다.</p>
            </div>
            <button className="save-button" type="button" onClick={save}>체크리스트 저장</button>
          </div>
          <div className="add-checklist">
            <input
              type="text"
              value={newItem}
              placeholder="추가할 자료명을 입력하세요"
              onChange={(event) => setNewItem(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") addCustomItem();
              }}
            />
            <button type="button" onClick={addCustomItem}>자료 추가</button>
          </div>
          <div className="evidence-list">
            {checklistItems.map((item) => (
              <EvidenceItemV2
                key={typeof item === "string" ? item : item.name}
                item={item}
                value={items[typeof item === "string" ? item : item.name]}
                onUpload={uploadEvidence}
                onDelete={deleteEvidence}
              />
            ))}
          </div>
          {uploadingName && <p className="save-message">{uploadingName} 처리 중입니다. 모델 응답까지 잠시 걸릴 수 있습니다.</p>}
          {message && <p className="save-message">{message}</p>}
        </section>
      </section>
    </main>
  );
}

function CriteriaPage({ data, onBack, onSelect, onOpenReferences, onOpenReportEditor }) {
  const criteria = data.criteria || [];
  const totalRequired = criteria.reduce((sum, item) => sum + (item.evidence?.length || 0), 0);
  const totalUploaded = criteria.reduce((sum, item) => sum + evidenceSlotStats(item).uploaded, 0);
  const averageScore = criteria.length
    ? (criteria.reduce((sum, item) => sum + (item.currentScore4 || 1), 0) / criteria.length).toFixed(1)
    : "0.0";

  return (
    <main className="criteria-main">
      <section className="criteria-panel">
        <div className="criteria-toolbar">
          <button className="back-button" type="button" onClick={onBack}>대시보드</button>
          <div>
            <p>DAC 기준별 평가 관리</p>
            <h1>평가기준</h1>
          </div>
          <button className="save-button" type="button" onClick={onOpenReportEditor}>보고서 열기</button>
        </div>

        <div className="criteria-summary-strip">
          <article>
            <span>기준 평균</span>
            <strong>{averageScore}/4</strong>
          </article>
          <article>
            <span>증빙 커버리지</span>
            <strong>{totalUploaded}/{totalRequired}</strong>
          </article>
          <article>
            <span>관리 상태</span>
            <strong>{data.overall.koicaGrade}</strong>
          </article>
        </div>

        <div className="criteria-table-panel">
          <div className="criteria-table-head">
            <span>평가 기준</span>
            <span>점수</span>
            <span>증빙</span>
            <span>현재 보완 필요사항</span>
            <span>작업</span>
          </div>
          {criteria.map((item) => {
            const evidenceStatus = item.evidenceStatus || {};
            const missingSlots = (item.evidence || [])
              .filter((document) => !evidenceStatus[document.name])
              .slice(0, 3);
            const card = data.insights?.criterionCards?.find((criterion) => criterion.id === item.id);
            const needs = card?.improvementNeeds?.length
              ? card.improvementNeeds.map((name) => ({ name }))
              : missingSlots;
            const { uploaded, required, coverage } = evidenceSlotStats(item);
            return (
              <article className="criteria-row" key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.scoreStatus || "검토 필요"}</p>
                </div>
                <b>{formatScore(item.currentScore4 || 1)}/4</b>
                <div>
                  <strong>{uploaded}/{required}</strong>
                  <ProgressBar value={coverage} />
                </div>
                <ul>
                  {needs.length ? needs.map((document) => (
                    <li key={document.name}>{document.name}</li>
                  )) : <li>{(item.currentScore4 || 1) < 4 ? "평가 초안 보완사항 확인 필요" : "주요 증빙 업로드 완료"}</li>}
                </ul>
                <div className="criteria-row-actions">
                  <button type="button" onClick={() => onSelect(item.id)}>상세</button>
                  <button type="button" onClick={onOpenReferences}>자료</button>
                </div>
              </article>
            );
          })}
        </div>

        <section className="criteria-standards-panel">
          <div className="criteria-section-head">
            <h2>기준별 채점 기준</h2>
            <p>상세 작업 화면에서 쓰는 핵심 정의, 공통 1~4점 기준, 세부 평가질문별 루브릭입니다.</p>
          </div>
          {criteria.map((item) => (
            <article className="criteria-standard-card" key={item.id}>
              <div className="criteria-standard-title">
                <div>
                  <h3>{item.name}</h3>
                  <p>{item.definition}</p>
                </div>
                <strong>{formatScore(item.currentScore4 || 1)}/4</strong>
              </div>
              {item.commonScoringNotes?.length > 0 && (
                <div className="common-score-grid criteria-common-score-grid">
                  {item.commonScoringNotes.map((note) => (
                    <article key={note.score}>
                      <strong>{note.score}</strong>
                      <p>{note.criteria}</p>
                    </article>
                  ))}
                </div>
              )}
              {item.scoringRubric?.length > 0 && (
                <div className="question-rubrics criteria-question-rubrics">
                  {item.scoringRubric.map((rubric) => (
                    <section key={rubric.question} className="rubric-card">
                      <h3>{rubric.question}</h3>
                      <div className="rubric-levels">
                        {rubric.levels.map((level) => (
                          <div key={level.score}>
                            <span>{level.score}</span>
                            <p>{level.criteria}</p>
                          </div>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}

let rhwpRequestId = 0;

function createRhwpBridge(iframe) {
  const pending = new Map();
  const onMessage = (event) => {
    if (event.data?.type === "rhwp-safe-save-request") {
      window.dispatchEvent(new CustomEvent("rhwp-safe-save-request"));
      return;
    }
    if (event.data?.type !== "rhwp-response" || event.data.id == null) return;
    const item = pending.get(event.data.id);
    if (!item) return;
    pending.delete(event.data.id);
    if (event.data.error) item.reject(new Error(event.data.error));
    else item.resolve(event.data.result);
  };
  window.addEventListener("message", onMessage);

  function request(method, params = {}, timeoutMs = 20000) {
    return new Promise((resolve, reject) => {
      const id = ++rhwpRequestId;
      pending.set(id, { resolve, reject });
      iframe.contentWindow.postMessage({ type: "rhwp-request", id, method, params }, "*");
      setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        reject(new Error(`${method} 응답 시간이 초과되었습니다.`));
      }, timeoutMs);
    });
  }

  return {
    async ready() {
      for (let index = 0; index < 40; index += 1) {
        try {
          const ok = await request("ready", {}, 5000);
          if (ok) return true;
        } catch (_error) {
          // rhwp-studio WASM 초기화 대기
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      throw new Error("rhwp 에디터 초기화 시간이 초과되었습니다.");
    },
    async loadFile(buffer, fileName) {
      return request("loadFile", { data: Array.from(new Uint8Array(buffer)), fileName, skipUnsavedGuard: true }, 60000);
    },
    async exportHwpVerify() {
      return request("exportHwpVerify", {}, 60000);
    },
    async exportHwp() {
      const result = await request("exportHwp", {}, 60000);
      return new Uint8Array(result || []);
    },
    async exportHwpx() {
      const result = await request("exportHwpx", {}, 60000);
      return new Uint8Array(result || []);
    },
    async scrollToPage(pageIndex, pageCount = 0) {
      return request("scrollToPage", { pageIndex, pageCount }, 5000);
    },
    async getSectionCount() {
      return request("getSectionCount", {}, 30000);
    },
    async getParagraphCount(sec) {
      return request("getParagraphCount", { sec }, 30000);
    },
    async getParagraphLength(sec, para) {
      return request("getParagraphLength", { sec, para }, 30000);
    },
    async getTextRange(sec, para, charOffset = 0, length = 9999) {
      return request("getTextRange", { sec, para, charOffset, length }, 30000);
    },
    async searchAllText(query, options = {}) {
      return request("searchAllText", { query, ...options }, 30000);
    },
    async replaceAll(query, newText, options = {}) {
      return request("replaceAll", { query, newText, ...options }, 60000);
    },
    async replaceText(hit, newText) {
      return request("replaceText", {
        sec: hit.sec ?? hit.sectionIndex ?? 0,
        para: hit.para ?? hit.paragraphIndex ?? 0,
        charOffset: hit.charOffset ?? hit.offset ?? hit.start ?? 0,
        length: hit.length ?? hit.len ?? hit.textLength ?? 0,
        newText,
      }, 60000);
    },
    async applyCharFormat(hit, format) {
      return request("applyCharFormat", {
        sec: hit.sec ?? hit.sectionIndex ?? 0,
        para: hit.para ?? hit.paragraphIndex ?? 0,
        charOffset: hit.charOffset ?? hit.offset ?? hit.start ?? 0,
        length: hit.length ?? hit.len ?? hit.textLength ?? 0,
        format,
      }, 60000);
    },
    async getFieldList() {
      return request("getFieldList", {}, 30000);
    },
    async setFieldValueByName(name, value) {
      return request("setFieldValueByName", { name, value }, 30000);
    },
    async setFieldValue(fieldId, value) {
      return request("setFieldValue", { fieldId, value }, 30000);
    },
    async getCellParagraphCount(cell) {
      return request("getCellParagraphCount", cell, 30000);
    },
    async getCellParagraphLength(cell) {
      return request("getCellParagraphLength", cell, 30000);
    },
    async getTextInCell(cell, length = 9999) {
      return request("getTextInCell", { ...cell, length }, 30000);
    },
    async deleteTextInCell(cell, length) {
      return request("deleteTextInCell", { ...cell, length }, 30000);
    },
    async insertTextInCell(cell, text) {
      return request("insertTextInCell", { ...cell, text }, 30000);
    },
    async deleteShapeControl(control) {
      return request("deleteShapeControl", control, 30000);
    },
    async deletePictureControl(control) {
      return request("deletePictureControl", control, 30000);
    },
    destroy() {
      window.removeEventListener("message", onMessage);
      pending.clear();
    },
  };
}

function downloadBytes(bytes, fileName, mimeType = "application/octet-stream") {
  const blob = new Blob([bytes], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function downloadDirect(url) {
  const frame = document.createElement("iframe");
  frame.style.display = "none";
  frame.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
  document.body.appendChild(frame);
  window.setTimeout(() => frame.remove(), 60000);
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(value || "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function reportSectionsToText(sections) {
  return sections
    .map((section) => `${section.title || ""}\n${section.body || ""}`.trim())
    .filter(Boolean)
    .join("\n\n");
}

function sectionMapFromList(sections) {
  return sections.reduce((map, section) => {
    if (section.id) map[section.id] = section;
    return map;
  }, {});
}

const REPORT_PART_PAGE_INDEX = {
  title: 0,
  cover: 0,
  toc: 1,
  notice: 2,
  grade: 2,
  "summary-ko": 3,
  summary: 3,
  "project-background": 5,
  "project-overview": 6,
  pdm: 7,
  "eval-purpose": 8,
  "eval-matrix": 9,
  "eval-methods": 10,
  "eval-limitations": 11,
  "eval-team": 12,
  achievement: 13,
  "criteria-relevance": 14,
  "criteria-coherence": 14,
  "criteria-effectiveness": 14,
  "criteria-efficiency": 15,
  "criteria-sustainability": 15,
  "criteria-crosscutting": 15,
  "criteria-other": 15,
  conclusion: 16,
  "working-factors": 17,
  "nonworking-factors": 17,
  theory: 18,
  feedback: 19,
  lessons: 19,
};

const REPORT_PART_TOC_PAGE_KEYS = {
  "summary-ko": "summary_ko_page",
  summary: "summary_ko_page",
  "project-background": "project_background_page",
  "project-overview": "project_overview_page",
  pdm: "pdm_page",
  "eval-purpose": "evaluation_purpose_page",
  "eval-matrix": "evaluation_matrix_page",
  "eval-methods": "evaluation_methods_page",
  "eval-limitations": "evaluation_limitations_page",
  "eval-team": "evaluation_team_page",
  achievement: "achievement_page",
  "criteria-relevance": "criteria_relevance_page",
  "criteria-coherence": "criteria_coherence_page",
  "criteria-effectiveness": "criteria_effectiveness_page",
  "criteria-efficiency": "criteria_efficiency_page",
  "criteria-sustainability": "criteria_sustainability_page",
  "criteria-crosscutting": "criteria_crosscutting_page",
  "criteria-other": "criteria_crosscutting_page",
  conclusion: "conclusion_page",
  "working-factors": "factors_page",
  "nonworking-factors": "factors_page",
  theory: "factors_page",
  feedback: "feedback_lessons_page",
  lessons: "feedback_lessons_page",
};

function tocPageIndex(partId, sectionId, tocPageMap) {
  const key = REPORT_PART_TOC_PAGE_KEYS[partId] || REPORT_PART_TOC_PAGE_KEYS[sectionId];
  const page = Number(key ? tocPageMap?.[key] : 0);
  return Number.isFinite(page) && page > 0 ? page - 1 : null;
}

function reportPartPageIndex(partId, sectionId, tocPageMap = {}) {
  if (partId === "grade" || sectionId === "grade") {
    const summaryPage = Number(tocPageMap?.summary_ko_page);
    if (Number.isFinite(summaryPage) && summaryPage > 3) return summaryPage - 3;
  }
  const tocIndex = tocPageIndex(partId, sectionId, tocPageMap);
  if (tocIndex != null) return tocIndex;
  if (Object.prototype.hasOwnProperty.call(REPORT_PART_PAGE_INDEX, partId)) return REPORT_PART_PAGE_INDEX[partId];
  if (Object.prototype.hasOwnProperty.call(REPORT_PART_PAGE_INDEX, sectionId)) return REPORT_PART_PAGE_INDEX[sectionId];
  return 0;
}

function normalizeRhwpFieldList(result) {
  let value = result;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch (_error) {
      return [];
    }
  }
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.fields)) return value.fields;
  if (Array.isArray(value?.items)) return value.items;
  return [];
}

function fieldIdentifier(field, index) {
  const candidates = [
    field?.fieldId,
    field?.id,
    field?.field_id,
    field?.ctrlId,
    field?.controlId,
    field?.index,
  ];
  const found = candidates.find((value) => Number.isInteger(Number(value)));
  return found == null ? index : Number(found);
}

function compactFieldText(value, maxLength) {
  const text = String(value || "")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!text) return "확인 중";
  if (!maxLength || text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}\n\n확인 중: 제출 전 근거자료를 보강하고 본문을 확정하세요.`;
}

function compactTableText(value, maxLength = 42) {
  const text = String(value || "")
    .replace(/\r?\n+/g, " ")
    .replace(/\.{3,}|…/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || text.length <= maxLength) return text;
  const firstSentence = text.match(/^.+?(?:함|됨|있음|없음|필요|확인됨|판단됨|\.)(?=\s|$)/)?.[0];
  const candidate = firstSentence && firstSentence.length <= maxLength ? firstSentence : text;
  const cut = candidate.lastIndexOf(" ", maxLength);
  const clipped = candidate.slice(0, cut > maxLength * 0.55 ? cut : maxLength).trim().replace(/[,:;·/-]+$/g, "");
  return /(?:함|됨|있음|없음|필요|확인됨|판단됨|\.)$/.test(clipped)
    ? clipped.replace(/\.$/, "") + "."
    : `${clipped}으로 판단됨.`;
}

function criterionTableReason(name, summary) {
  const text = compactTableText(summary, 56);
  if (!text || /자료 업로드|확인 중|필수 증빙|증빙/.test(text)) {
    return `${name} 근거 미흡. 보완 필요.`;
  }
  return text.endsWith(".") ? text : `${text}.`;
}

function wrapRhwpTitle(value, maxLineLength = 24) {
  const words = String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (line && next.length > maxLineLength) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines.join("\n");
}

function sectionBody(byId, id, maxLength) {
  return compactFieldText(byId[id]?.body, maxLength);
}

const EDITOR_PART_HEADING_REGEX = {
  summary: [/^I\.?\s*평가결과\s*요약.*$/i, /^1\.?\s*국문\s*요약$/i],
  "summary-ko": [/^I\.?\s*평가결과\s*요약.*$/i, /^1\.?\s*국문\s*요약$/i],
  "project-background": [/^II\.?\s*대상사업\s*개요.*$/i, /^1\.?\s*사업\s*추진배경$/i],
  "project-overview": [/^II\.?\s*대상사업\s*개요.*$/i, /^2\.?\s*사업\s*개요$/i, /^2\.?\s*사업개요$/i],
  pdm: [/^II\.?\s*대상사업\s*개요.*$/i, /^3\.?\s*사업설계매트릭스\s*\(?PDM\)?$/i],
  "eval-purpose": [/^III\.?\s*평가개요.*$/i, /^1\.?\s*평가\s*목적과\s*범위$/i],
  "eval-matrix": [/^III\.?\s*평가개요.*$/i, /^2\.?\s*평가\s*매트릭스.*$/i],
  "eval-methods": [/^III\.?\s*평가개요.*$/i, /^3\.?\s*평가\s*방법$/i],
  "eval-limitations": [/^III\.?\s*평가개요.*$/i, /^4\.?\s*평가\s*한계$/i],
  "eval-team": [/^III\.?\s*평가개요.*$/i, /^5\.?\s*평가단\s*구성\s*및\s*수행체계$/i],
  achievement: [/^IV\.?\s*성과\s*달성/i],
  "criteria-relevance": [/^V\.?\s*기준별\s*평가결과.*$/i, /^1\.?\s*적절성/i],
  "criteria-coherence": [/^V\.?\s*기준별\s*평가결과.*$/i, /^2\.?\s*일관성/i],
  "criteria-effectiveness": [/^V\.?\s*기준별\s*평가결과.*$/i, /^3\.?\s*효과성/i],
  "criteria-efficiency": [/^V\.?\s*기준별\s*평가결과.*$/i, /^4\.?\s*효율성/i],
  "criteria-sustainability": [/^V\.?\s*기준별\s*평가결과.*$/i, /^5\.?\s*지속가능성/i],
  "criteria-crosscutting": [/^V\.?\s*기준별\s*평가결과.*$/i, /^6\.?\s*범분야\s*이슈/i],
  "criteria-other": [/^V\.?\s*기준별\s*평가결과.*$/i, /^7\.?\s*그\s*외\s*평가기준$/i],
  conclusion: [/^(VI|IV)\.?\s*결론.*$/i, /^1\.?\s*결론.*$/i],
  "working-factors": [/^(VI|IV)\.?\s*결론.*$/i, /^2\.?\s*작동요인\s*및\s*비작동요인/i, /^\(?1\)?\s*작동\s*요인$/i],
  "nonworking-factors": [/^(VI|IV)\.?\s*결론.*$/i, /^2\.?\s*작동요인\s*및\s*비작동요인/i, /^\(?2\)?\s*비작동\s*요인$/i],
  theory: [/^(VI|IV)\.?\s*결론.*$/i, /^\(?3\)?\s*변화이론\s*분석$/i],
  feedback: [/^(VI|IV)\.?\s*결론.*$/i, /^3\.?\s*환류과제\s*및\s*교훈$/i, /^\(?1\)?\s*환류과제$/i],
  lessons: [/^(VI|IV)\.?\s*결론.*$/i, /^3\.?\s*환류과제\s*및\s*교훈$/i, /^\(?2\)?\s*교훈$/i],
};

function stripEditorPartHeadings(value, partId) {
  const patterns = EDITOR_PART_HEADING_REGEX[partId] || [];
  if (!patterns.length) return String(value || "").trim();
  const kept = [];
  let skipped = false;
  for (const line of String(value || "").replace(/\r\n?/g, "\n").split("\n")) {
    const normalized = line.trim();
    if (normalized && patterns.some((pattern) => pattern.test(normalized))) {
      skipped = true;
      continue;
    }
    if (skipped && !normalized && !kept.length) continue;
    kept.push(line.replace(/\s+$/, ""));
  }
  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function criterionById(payload, id) {
  return (payload?.criteria || []).find((item) => item.id === id) || {};
}

function criterionSummary(payload, id, fallbackName) {
  const item = criterionById(payload, id);
  const score = Number(item.currentScore4 || item.score || 1);
  const name = item.name || fallbackName;
  const evaluation = item.evaluationResult || {};
  const questionRows = Array.isArray(evaluation.questionAssessments)
    ? evaluation.questionAssessments.map((assessment, index) => ({
        score: Number(assessment?.score || score || 1),
        reason: compactTableText(assessment?.finding || assessment?.judgement || assessment?.summary || assessment?.question || name, 260),
        question: assessment?.question || `Q${index + 1}`,
      }))
    : [];
  const summary = item.summary || evaluation.summary || `${name} 근거자료가 부족하여 보수적으로 ${formatScore(score)}/4점으로 산정했습니다.`;
  return {
    id,
    name,
    score,
    reason: compactFieldText(summary, 180),
    tableReason: criterionTableReason(name, summary),
    questionRows,
  };
}

function buildRhwpAutoFillPlan(payload) {
  const project = payload?.project || {};
  const title = project.title || "??? ?? ?";
  const wrappedTitle = wrapRhwpTitle(title, 24);
  const period = project.period || "?? ?? ?";
  const budget = project.budget || "?? ?? ?";
  const today = new Date();
  const yearMonth = `${today.getFullYear()}. ${String(today.getMonth() + 1).padStart(2, "0")}`;

  return {
    title,
    wrappedTitle,
    titleFontSize: coverTitleFontSize(title),
    placeholders: [
      ["{????}", wrappedTitle],
      ["????? ???? ?????", `${wrappedTitle}\n???? ?????`],
      ["2023. 12", yearMonth],
      ["???(????/??)", `${title}(${period} / ${budget})`],
      ["????? OOO", "?????/???? ?? ?"],
      ["?????? OOO(??)", ""],
    ],
    fields: [
      ["???", wrappedTitle],
      ["????", period],
      ["??", budget],
      ["?????", "?????/???? ?? ?"],
      ["??????", ""],
    ],
  };
}

const REPORT_EDITOR_APPLY_PART_IDS = [
  "cover",
  "toc",
  "notice",
  "grade",
  "summary-ko",
  "project-background",
  "project-overview",
  "pdm",
  "eval-purpose",
  "eval-matrix",
  "eval-methods",
  "eval-limitations",
  "eval-team",
  "achievement",
  "criteria-relevance",
  "criteria-coherence",
  "criteria-effectiveness",
  "criteria-efficiency",
  "criteria-sustainability",
  "criteria-crosscutting",
  "criteria-other",
  "conclusion",
  "working-factors",
  "nonworking-factors",
  "theory",
  "feedback",
  "lessons",
];

function buildRhwpBodyFillPlan(payload, sections) {
  const byId = sectionMapFromList(sections);
  const project = payload?.project || {};
  const projectLabel = `${project.title || "사업명 확인 중"}(${project.period || "기간 확인 중"} / ${project.budget || "예산 확인 중"})`;
  const criteria = [
    criterionSummary(payload, "relevance", "적절성"),
    criterionSummary(payload, "coherence", "일관성"),
    criterionSummary(payload, "effectiveness", "효과성"),
    criterionSummary(payload, "efficiency", "효율성"),
    criterionSummary(payload, "sustainability", "지속가능성"),
  ];
  const totalScore = criteria.reduce((sum, item) => sum + (Number(item.score) || 1), 0);
  const feedbackLines = sectionBody(byId, "feedback", 1200).split("\n").filter(Boolean).slice(0, 6);
  const lessonLines = sectionBody(byId, "lessons", 1200).split("\n").filter(Boolean).slice(0, 6);
  const factorBody = sectionBody(byId, "factors", 2200);
  const workedFactorText = factorBody.split("[비작동요인]")[0].replace("[작동요인]", "").trim();
  const notWorkedFactorText = (factorBody.split("[비작동요인]")[1] || factorBody).trim();
  const projectTitle = project.title || "사업명 확인 중";
  const wrappedTitle = wrapRhwpTitle(projectTitle, 24);
  const reportTitle = `${wrappedTitle}\n종료평가 결과보고서`;
  const criteriaCombined = [
    sectionBody(byId, "criteria-relevance", 1600),
    sectionBody(byId, "criteria-coherence", 1600),
    sectionBody(byId, "criteria-effectiveness", 1600),
    sectionBody(byId, "criteria-efficiency", 1600),
    sectionBody(byId, "criteria-sustainability", 1600),
    sectionBody(byId, "criteria-crosscutting", 1200),
    sectionBody(byId, "criteria-other", 1200),
  ].filter(Boolean).join("\n\n");
  const factorsCombined = [
    sectionBody(byId, "working-factors", 1400),
    sectionBody(byId, "nonworking-factors", 1400),
    sectionBody(byId, "theory", 1400),
  ].filter(Boolean).join("\n\n");
  const evalMatrixRows = [
    [6, 7, 8, 9],
    [11, 12, 13, 14],
    [16, 17, 18, 19],
    [21, 22, 23, 24],
    [26, 27, 28, 29],
  ];
  return {
    partIds: REPORT_EDITOR_APPLY_PART_IDS,
    headingInserts: [
      { id: "toc", anchors: ["??"], minSec: 2, text: sectionBody(byId, "toc", 1200), maxLength: 1200, headingText: "??" },
      { id: "notice", anchors: ["????? ?? ??"], minSec: 2, text: sectionBody(byId, "notice", 1600), maxLength: 1600, headingText: "????? ?? ??" },
      { id: "summary", anchors: ["1. ?? ??", "?? ??"], minSec: 3, text: sectionBody(byId, "summary", 4200), maxLength: 4200 },
      { id: "project-background", anchors: ["1. ?? ????", "?? ????"], minSec: 3, text: sectionBody(byId, "project-background", 2600), maxLength: 2600 },
      { id: "pdm", anchors: ["3. ????????(PDM)", "????????(PDM)"], minSec: 4, text: sectionBody(byId, "pdm", 2400), maxLength: 2400 },
      { id: "eval-purpose", anchors: ["1. ??? ??? ??", "??? ??? ??"], minSec: 4, text: sectionBody(byId, "eval-purpose", 2200), maxLength: 2200 },
      { id: "eval-matrix", anchors: ["2. ??????", "?? ????"], minSec: 4, text: sectionBody(byId, "eval-matrix", 2600), maxLength: 2600 },
      { id: "eval-methods", anchors: ["3. ????", "?? ??"], minSec: 4, text: sectionBody(byId, "eval-methods", 2200), maxLength: 2200 },
      { id: "eval-limitations", anchors: ["4. ??? ??", "?? ??"], minSec: 4, text: sectionBody(byId, "eval-limitations", 1800), maxLength: 1800 },
      { id: "eval-team", anchors: ["5. ??? ??", "??? ?? ? ????"], minSec: 4, text: sectionBody(byId, "eval-team", 1800), maxLength: 1800 },
      { id: "criteria-relevance", anchors: ["1. ???", "???"], minSec: 6, text: sectionBody(byId, "criteria-relevance", 2200), maxLength: 2200 },
      { id: "criteria-coherence", anchors: ["2. ???", "???"], minSec: 6, text: sectionBody(byId, "criteria-coherence", 2200), maxLength: 2200 },
      { id: "criteria-effectiveness", anchors: ["3. ???", "???"], minSec: 6, text: sectionBody(byId, "criteria-effectiveness", 2200), maxLength: 2200 },
      { id: "criteria-efficiency", anchors: ["4. ???", "???"], minSec: 6, text: sectionBody(byId, "criteria-efficiency", 2200), maxLength: 2200 },
      { id: "criteria-sustainability", anchors: ["5. ?????", "?????"], minSec: 6, text: sectionBody(byId, "criteria-sustainability", 2200), maxLength: 2200 },
      { id: "criteria-crosscutting", anchors: ["6. ??? ??", "??? ??"], minSec: 6, text: sectionBody(byId, "criteria-crosscutting", 1800), maxLength: 1800 },
      { id: "criteria-other", anchors: ["7. ? ? ????", "? ? ????"], minSec: 6, text: sectionBody(byId, "criteria-other", 1600), maxLength: 1600 },
      { id: "conclusion", anchors: ["1. ??", "??"], minSec: 7, text: sectionBody(byId, "conclusion", 2200), maxLength: 2200 },
      { id: "working-factors", anchors: ["(1) ????", "????"], minSec: 7, text: sectionBody(byId, "working-factors", 1800), maxLength: 1800 },
      { id: "nonworking-factors", anchors: ["(2) ?????", "?????"], minSec: 7, text: sectionBody(byId, "nonworking-factors", 1800), maxLength: 1800 },
      { id: "theory", anchors: ["(3) ???? ??", "???? ??"], minSec: 8, text: sectionBody(byId, "theory", 2200), maxLength: 2200 },
      { id: "feedback", anchors: ["(1) ????", "????"], minSec: 8, text: sectionBody(byId, "feedback", 2200), maxLength: 2200 },
      { id: "lessons", anchors: ["(2) ??", "??"], minSec: 8, text: sectionBody(byId, "lessons", 2200), maxLength: 2200 },
    ],
    paragraphInserts: [
      { id: "summary-ko", label: "국문 요약", sec: 3, para: 3, text: sectionBody(byId, "summary", 4200) },
      { label: "첨부 영문 요약", sec: 9, para: 8, text: sectionBody(byId, "annex-en", 2200) },
    ],
    guideCleanups: [
      { label: "summary-guide-block-1", sec: 3, para: 3, length: 2200, text: "", query: "보고서 주요 내용 위주로 3~5쪽 이내 요약 작성" },
      { label: "summary-guide-block-2", sec: 3, para: 4, length: 1800, text: "", query: "개별 사업별 AI 기반 ODA 성과관리 평가 자동화 프로그램 개발" },
      { label: "summary-guide-block-3", sec: 3, para: 5, length: 1800, text: "" },
      { label: "conclusion-guide-1", sec: 7, para: 28, length: 35, text: sectionBody(byId, "conclusion", 1600), query: "결론 및 평가목표와 대상사업의 전반적 목표 관련 내용" },
      { label: "conclusion-guide-2", sec: 7, para: 29, length: 47, text: "", query: "결론에서 본문에 없는 새로운 이슈를 제시하는 안내문" },
      { label: "criteria-result-guide", sec: 6, para: 4, length: 38, text: criteriaCombined || sectionBody(byId, "criteria", 3200), query: "평가매트릭스 평가질문별 평가결과 표시" },
      { label: "achievement-example-title", sec: 5, para: 1, length: 20, text: "", query: "작성 예시 보고서 작성 제목" },
      { label: "worked-guide", sec: 7, para: 36, length: 61, text: sectionBody(byId, "working-factors", 1800) || workedFactorText, query: "평가결과를 기반으로 사업 성과달성에 기여한 요인과 그 원인 표시" },
      { label: "not-worked-guide", sec: 7, para: 42, length: 86, text: sectionBody(byId, "nonworking-factors", 1800) || notWorkedFactorText, query: "평가결과를 기반으로 사업 성과달성을 저해한 요인 표시" },
      { label: "theory-guide", sec: 8, para: 1, length: 106, text: sectionBody(byId, "theory", 1600) },
      { label: "theory-example-title", sec: 8, para: 3, length: 32, text: "", query: "작성 예시 사업 종료단계 분석" },
      { label: "theory-example-title-2", sec: 8, para: 11, length: 50, text: "", query: "작성 예시 사업종료단계 및 To-Be 변화이론 모델 분석" },
    ],
    deleteControls: [
      { label: "eval-overview-tip-box", type: "shape", sec: 4, para: 48, controlIndex: 0 },
      { label: "efficiency-reference-box", type: "shape", sec: 7, para: 3, controlIndex: 0 },
      { label: "criteria-result-tip-box", type: "shape", sec: 7, para: 17, controlIndex: 0 },
      { label: "worked-example-box", type: "shape", sec: 7, para: 38, controlIndex: 0 },
      { label: "not-worked-example-box", type: "shape", sec: 7, para: 44, controlIndex: 0 },
      { label: "theory-example-image", type: "picture", sec: 8, para: 5, controlIndex: 0 },
      { label: "theory-example-image-2", type: "picture", sec: 8, para: 12, controlIndex: 0 },
      { label: "theory-example-image-3", type: "picture", sec: 8, para: 13, controlIndex: 0 },
      { label: "conclusion-tip-box", type: "shape", sec: 8, para: 22, controlIndex: 0 },
    ],
    residualReplacements: [
      { query: "평가대상 사업명", text: "" },
      { query: "평가대상 사업명:", text: "" },
      { query: "종합점수:", text: "" },
      { query: "종합점수 :", text: "" },
      { query: "KOICA 평가등급:", text: "" },
      { query: "KOICA 평가등급 :", text: "" },
      { query: "국무조정실 평가등급:", text: "" },
      { query: "국무조정실 평가등급 :", text: "" },
      { query: "점수 산정근거: 업로드 증빙, 기준별 평가의견, 전략자료 현황을 종합하여 산정함", text: "" },
      { query: "적절성(Relevance) - 1~4점", text: "" },
      { query: "일관성(Coherence) - 1~4점", text: "" },
      { query: "효과성(Effectiveness) - 1~4점", text: "" },
      { query: "효율성(Efficiency) - 1~4점", text: "" },
      { query: "지속가능성(Sustainability) - 1~4점", text: "" },
      { query: "평가의견:", text: "" },
      { query: "적용근거:", text: "" },
      { query: "보완 필요사항:", text: "" },
      { query: "〇〇사업 종료평가 결과보고서", text: reportTitle },
      { query: "〇〇사업 종료평가", text: `${wrappedTitle}\n종료평가` },
      { query: "〇〇사업", text: projectTitle },
      { query: "{사업이름}", text: projectTitle },
      { query: "2023. 12", text: new Date().toISOString().slice(0, 7).replace("-", ". ") },
      { query: "평가책임자 OOO", text: "평가책임자 확인 중" },
      { query: "평가수행기관 OOO(로고)", text: "평가수행기관 확인 중" },
      { query: "OOO", text: "확인 중" },
      { query: "보고서 작성완료 후 쪽수 수정", text: "" },
      { query: "보고서 작성 TIP", text: "" },
      { query: "보고서 주요 내용 위주로 3~5쪽 이내 요약 작성", text: "" },
      { query: "개별 사업별 AI 기반 ODA 성과관리 평가 자동화 프로그램 개발", text: "" },
      { query: "효율성 평가 여부 및 참고문헌", text: "" },
      { query: "작동요인 작성 예시", text: "" },
      { query: "비작동요인 작성 예시", text: "" },
      { query: "OECD DAC 6대 평가범주 정의 및 유의사항", text: "" },
    ],
    fieldInserts: [
      { label: "대상사업 개요 - 사업 추진배경", fieldOrder: 1, text: sectionBody(byId, "project-background", 1800) },
      { label: "대상사업 개요 - 사업 추진배경 근거", fieldOrder: 2, text: "확인 중: 사업 추진배경의 문헌 출처, 수원기관 수요자료, 현지 문제분석 근거를 확인해 주세요." },
      { label: "대상사업 개요 - 사업개요", fieldOrder: 3, text: sectionBody(byId, "project-overview", 1600) },
      { label: "사업설계매트릭스(PDM)", fieldOrder: 4, text: sectionBody(byId, "pdm", 1800) },
      { label: "평가 목적과 범위", fieldOrder: 5, text: sectionBody(byId, "eval-purpose", 1400) },
      { label: "평가 방법", fieldOrder: 6, text: sectionBody(byId, "eval-methods", 1400) },
      { label: "기준별 평가결과", fieldOrder: 7, text: sectionBody(byId, "criteria", 3200) },
    ],
    tableCells: [
      { label: "평가등급표 총점", sec: 2, para: 9, controlIndex: 0, cellIndex: 74, text: `${totalScore}/20점` },
      { label: "종합 평가 등급", sec: 2, para: 9, controlIndex: 0, cellIndex: 76, text: payload?.overall?.governmentGrade || "미정" },
      { label: "KOICA 평가등급", sec: 2, para: 9, controlIndex: 0, cellIndex: 78, text: payload?.overall?.koicaGrade || "F" },
      { label: "사업명 국문", sec: 3, para: 49, controlIndex: 0, cellIndex: 4, text: project.title || "확인 중" },
      { label: "사업명 영문", sec: 3, para: 49, controlIndex: 0, cellIndex: 6, text: "Additional information required" },
      { label: "대상국가", sec: 3, para: 49, controlIndex: 0, cellIndex: 8, text: "확인 중: 대상국가 및 대상지역" },
      { label: "사업기간/예산", sec: 3, para: 49, controlIndex: 0, cellIndex: 10, text: `구분 : 신규/계속 확인 필요\n기간 : ${project.period || "확인 중"}\n총 사업예산 : ${project.budget || "확인 중"}` },
      { label: "사업분야", sec: 3, para: 49, controlIndex: 0, cellIndex: 14, text: "성과관리/평가" },
      { label: "사업목적", sec: 3, para: 49, controlIndex: 0, cellIndex: 16, text: compactFieldText(sectionBody(byId, "project-overview", 300), 300) },
      { label: "수원국 분담사항", sec: 3, para: 49, controlIndex: 0, cellIndex: 31, text: "확인 중: 수원국 파트너 기관 분담사항 확인" },
      { label: "PDM 영향 요약", sec: 4, para: 4, controlIndex: 0, cellIndex: 8, text: `${project.title || "대상사업"}의 장기 개발효과. 구체적 영향문장은 PDM 또는 사업개요 확인 필요.` },
      { label: "PDM 성과 요약", sec: 4, para: 4, controlIndex: 0, cellIndex: 13, text: compactFieldText(sectionBody(byId, "project-overview", 260), 260) },
      { label: "PDM 산출물 요약", sec: 4, para: 4, controlIndex: 0, cellIndex: 18, text: "확인 중: 산출물, 활동, 수혜자별 산출 목표를 확인할 수 있는 PDM 또는 성과관리자료 필요." },
      { label: "PDM 활동", sec: 4, para: 4, controlIndex: 0, cellIndex: 22, text: "사업개요서, 수행계획서, 활동보고서 기준으로 주요 활동을 정리해야 함" },
      { label: "PDM 투입", sec: 4, para: 4, controlIndex: 0, cellIndex: 23, text: `예산: ${project.budget || "확인 중"}\n인력, 장비, 서비스 등 투입자료 추가 확인 필요.` },
      { label: "PDM 전제조건", sec: 4, para: 4, controlIndex: 0, cellIndex: 24, text: "수행기관 협조, 현지 자료 접근성, 이해관계자 참여, 데이터 품질 정보 필요." },
      { label: "성과달성 산출물 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 20, text: "산출물 1: 성과관리 평가 자료 구축 및 적용" },
      { label: "성과달성 지표 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 21, text: "적용 문서 수, 평가 자동처리 가능 범위" },
      { label: "성과달성 기초값 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 22, text: "확인 중" },
      { label: "성과달성 목표치 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 23, text: "확인 중" },
      { label: "성과달성 종료값 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 26, text: "확인 중" },
      { label: "성과달성 달성률 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 27, text: "확인 중" },
      { label: "성과달성 MOV 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 28, text: "사업개요서, 성과자료, 운영자료" },
      { label: "성과달성 비고 1", sec: 5, para: 2, controlIndex: 0, cellIndex: 29, text: "업로드 문서 보강 및 LLM 검토 필요" },
      { label: "성과달성 산출물 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 34, text: "산출물 2: 종료평가 보고서 작성 및 검토 체계" },
      { label: "성과달성 지표 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 35, text: "양식 준수, 기준별 근거 반영, 검토의견 반영 여부" },
      { label: "성과달성 기초값 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 36, text: "확인 중" },
      { label: "성과달성 목표치 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 37, text: "확인 중" },
      { label: "성과달성 종료값 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 40, text: "확인 중" },
      { label: "성과달성 달성률 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 41, text: "확인 중" },
      { label: "성과달성 MOV 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 42, text: "생성 보고서, rhwp 편집 이력, 검토의견 제출본" },
      { label: "성과달성 비고 2", sec: 5, para: 2, controlIndex: 0, cellIndex: 43, text: "근거자료 미업로드 시 보수적으로 판단" },
      ...criteria.flatMap((item, index) => {
        const scoreCells = [[6, 8, 10, 12, 14, 16], [19, 21, 23, 25, 27, 29], [32, 34, 36, 38, 40, 42, 44, 46], [49, 51, 53, 55, 57, 59], [62, 64, 66, 68, 70, 72]][index];
        const rows = [];
        for (let pairIndex = 0; pairIndex < scoreCells.length; pairIndex += 2) {
          const isTotalRow = pairIndex >= scoreCells.length - 2;
          const questionRow = item.questionRows?.[pairIndex / 2];
          const rowScore = isTotalRow ? item.score : (questionRow?.score || item.score);
          const rowReason = isTotalRow ? item.tableReason : (questionRow?.reason || item.tableReason);
          rows.push(
            { label: `평가등급표 ${index + 1}-${pairIndex / 2 + 1} 점수`, sec: 2, para: 9, controlIndex: 0, cellIndex: scoreCells[pairIndex], text: `${formatScore(rowScore)}점` },
            { label: `평가등급표 ${index + 1}-${pairIndex / 2 + 1} 선정이유`, sec: 2, para: 9, controlIndex: 0, cellIndex: scoreCells[pairIndex + 1], text: rowReason, maxLength: isTotalRow ? 90 : 260 },
          );
        }
        return rows;
      }),
      ...criteria.flatMap((item, index) => {
        const cells = evalMatrixRows[index];
        return [
          { label: `평가매트릭스 질문 ${index + 1}`, sec: 4, para: 23, controlIndex: 0, cellIndex: cells[0], text: `${item.name} 기준에서 사업 설계, 수행, 성과가 종료평가 기준에 부합하는가?` },
          { label: `평가매트릭스 지표 ${index + 1}`, sec: 4, para: 23, controlIndex: 0, cellIndex: cells[1], text: `${item.score}/4점, 증빙 충족도와 이해관계자 확인 여부, 성과자료 정합성` },
          { label: `평가매트릭스 자료출처 ${index + 1}`, sec: 4, para: 23, controlIndex: 0, cellIndex: cells[2], text: "사업개요서, PDM, 성과자료, 예산 및 운영자료, 면담 및 담당자 확인자료" },
          { label: `평가매트릭스 방법 ${index + 1}`, sec: 4, para: 23, controlIndex: 0, cellIndex: cells[3], text: "문헌검토, 기준별 채점, 증빙 교차검증, 미확인 항목 보완요청" },
        ];
      }),
      ...feedbackLines.slice(0, 3).flatMap((line, index) => {
        const base = 5 + index * 5;
        const cleanLine = String(line || "").replace(/^[-\s]+/, "");
        return [
          { label: `환류 관찰 ${index + 1}`, sec: 8, para: 17, controlIndex: 0, cellIndex: base, text: compactFieldText(line, 160) },
          { label: `환류 과제 ${index + 1}`, sec: 8, para: 17, controlIndex: 0, cellIndex: base + 1, text: compactFieldText(cleanLine, 160) },
          { label: `환류 부서 ${index + 1}`, sec: 8, para: 17, controlIndex: 0, cellIndex: base + 2, text: "사업담당부서/수행기관" },
          { label: `환류 사유 ${index + 1}`, sec: 8, para: 17, controlIndex: 0, cellIndex: base + 3, text: "평가결과 환류 및 후속 성과관리 강화" },
        ];
      }),
      ...lessonLines.slice(0, 3).flatMap((line, index) => {
        const rowCells = [[6, 9, 10], [11, 14, 15], [16, 19, 20]][index];
        const cleanLine = String(line || "").replace(/^[-\s]+/, "");
        return [
          { label: `교훈 관찰 ${index + 1}`, sec: 8, para: 20, controlIndex: 0, cellIndex: rowCells[0], text: compactFieldText(line, 140) },
          { label: `교훈 내용 ${index + 1}`, sec: 8, para: 20, controlIndex: 0, cellIndex: rowCells[1], text: compactFieldText(cleanLine, 180) },
          { label: `교훈 체크리스트 ${index + 1}`, sec: 8, para: 20, controlIndex: 0, cellIndex: rowCells[2], text: "후속 사업 설계에 반영 가능한 교훈인지 확인" },
        ];
      }),
    ],
  };
}

async function replaceTableCellText(bridge, item, text) {
  const baseCell = {
    sec: item.sec,
    para: item.para,
    controlIndex: item.controlIndex || 0,
    cellIndex: item.cellIndex,
    charOffset: 0,
  };
  let paragraphCount = 1;
  try {
    paragraphCount = Math.max(1, Number(await bridge.getCellParagraphCount(baseCell)) || 1);
  } catch (_error) {}
  for (let cellParaIndex = paragraphCount - 1; cellParaIndex >= 0; cellParaIndex -= 1) {
    const cell = { ...baseCell, cellParaIndex };
    let length = 0;
    try {
      length = Number(await bridge.getCellParagraphLength(cell)) || 0;
    } catch (_error) {
      try {
        const current = await bridge.getTextInCell(cell, 9999);
        length = String(current || "").length;
      } catch (_ignored) {
        length = 0;
      }
    }
    if (length > 0) {
      await bridge.deleteTextInCell(cell, length);
    }
  }
  await bridge.insertTextInCell(
    { ...baseCell, cellParaIndex: item.cellParaIndex || 0 },
    compactFieldText(text, item.maxLength || 700)
  );
}

async function replaceHeadingWithBody(bridge, item) {
  const anchors = Array.isArray(item.anchors) ? item.anchors : [item.anchor];
  for (const anchor of anchors.filter(Boolean)) {
    let hits = [];
    try {
      const result = await bridge.searchAllText(anchor, {});
      hits = Array.isArray(result) ? result : (result?.hits || result?.items || []);
    } catch (_error) {
      hits = [];
    }
    const target = hits
      .filter((hit) => Number(hit.sec ?? hit.sectionIndex ?? 0) >= (item.minSec || 0))
      .sort((a, b) => {
        const secA = Number(a.sec ?? a.sectionIndex ?? 0);
        const secB = Number(b.sec ?? b.sectionIndex ?? 0);
        const paraA = Number(a.para ?? a.paragraphIndex ?? 0);
        const paraB = Number(b.para ?? b.paragraphIndex ?? 0);
        return secA - secB || paraA - paraB;
      })[0];
    if (!target) continue;
    const text = compactFieldText(stripEditorPartHeadings(item.text, item.id), item.maxLength || 2600);
    if (!text) continue;
    const heading = item.headingText || anchor;
    const replacement = `${heading}\n\n${text}`;
    await bridge.replaceText({
      ...target,
      length: target.length || anchor.length,
    }, replacement);
    return true;
  }
  return false;
}

async function findReportPartNavigationTarget(bridge, item, fallbackQueries = []) {
  const anchors = Array.isArray(item?.anchors) ? item.anchors : [item?.anchor];
  const queries = [...anchors, ...fallbackQueries]
    .filter(Boolean)
    .map((query) => String(query).replace(/\s+/g, " ").trim())
    .filter(Boolean);
  for (const query of [...new Set(queries)]) {
    let hits = [];
    try {
      const result = await bridge.searchAllText(query, {});
      hits = Array.isArray(result) ? result : (result?.hits || result?.items || []);
    } catch (_error) {
      hits = [];
    }
    const target = hits
      .filter((hit) => Number(hit.sec ?? hit.sectionIndex ?? 0) >= (item?.minSec || 0))
      .sort((a, b) => {
        const pageA = Number(a.pageIndex ?? a.page ?? a.pageNo ?? 9999);
        const pageB = Number(b.pageIndex ?? b.page ?? b.pageNo ?? 9999);
        const secA = Number(a.sec ?? a.sectionIndex ?? 0);
        const secB = Number(b.sec ?? b.sectionIndex ?? 0);
        const paraA = Number(a.para ?? a.paragraphIndex ?? 0);
        const paraB = Number(b.para ?? b.paragraphIndex ?? 0);
        return pageA - pageB || secA - secB || paraA - paraB;
      })[0];
    if (!target) continue;
    const rawPage = target.pageIndex ?? target.page ?? target.pageNo;
    if (rawPage != null && Number.isFinite(Number(rawPage))) {
      const page = Number(rawPage);
      return { pageIndex: page > 0 && target.pageIndex == null ? page - 1 : page, hit: target, query };
    }
    return { hit: target, query };
  }
  return null;
}

function coverTitleFontSize(title) {
  const length = String(title || "").replace(/\s+/g, "").length;
  if (length > 46) return 1900;
  if (length > 34) return 2100;
  return 2300;
}

async function applyCoverTitleFit(bridge, title) {
  const fontSize = coverTitleFontSize(title);
  const queries = [
    String(title || "").replace(/\n/g, " ").trim(),
    ...String(title || "").split(/\n/).map((line) => line.trim()).filter((line) => line.length >= 4),
    "종료평가 결과보고서",
  ];
  for (const query of [...new Set(queries)].filter(Boolean)) {
    try {
      const result = await bridge.searchAllText(query, {});
      const hits = Array.isArray(result) ? result : (result?.hits || result?.items || []);
      for (const hit of hits.slice(0, 4)) {
        const sec = Number(hit.sec ?? hit.sectionIndex ?? 0);
        const para = Number(hit.para ?? hit.paragraphIndex ?? 0);
        if (sec > 1 || para > 12) continue;
        await bridge.applyCharFormat({
          ...hit,
          length: hit.length || query.length,
        }, { fontSize, height: fontSize, size: fontSize });
      }
    } catch (_error) {
      // 글자 크기 조정 API를 지원하지 않는 rhwp 빌드면 양식 기본값을 유지한다.
    }
  }
}

function inferTableCellPartId(item) {
  if (!item) return null;
  if (item.sec === 2) return "grade";
  if (item.sec === 3) return "project-overview";
  if (item.sec === 4 && item.para === 4) return "pdm";
  if (item.sec === 4 && item.para === 23) return "eval-matrix";
  if (item.sec === 5) return "achievement";
  if (item.sec === 8 && item.para === 17) return "feedback";
  if (item.sec === 8 && item.para === 20) return "lessons";
  return null;
}

function buildRhwpGradeTableCells(payload, sections) {
  const plan = buildRhwpBodyFillPlan(payload, sections);
  return (plan.tableCells || []).filter((item) =>
    item.sec === 2 && item.para === 9 && item.controlIndex === 0
  );
}

async function readEditorTextSnapshot(bridge, payload, sections) {
  const paragraphs = [];
  const cells = [];
  let sectionCount = 0;
  try {
    sectionCount = Number(await bridge.getSectionCount()) || 0;
  } catch (_error) {
    sectionCount = 0;
  }
  for (let sec = 0; sec < sectionCount; sec += 1) {
    let paragraphCount = 0;
    try {
      paragraphCount = Number(await bridge.getParagraphCount(sec)) || 0;
    } catch (_error) {
      paragraphCount = 0;
    }
    for (let para = 0; para < paragraphCount; para += 1) {
      try {
        const length = Number(await bridge.getParagraphLength(sec, para)) || 0;
        const text = length > 0 ? await bridge.getTextRange(sec, para, 0, Math.max(length, 9999)) : "";
        paragraphs.push({ sec, para, text: String(text || "") });
      } catch (_error) {
        paragraphs.push({ sec, para, text: "" });
      }
    }
  }

  const plan = buildRhwpBodyFillPlan(payload, sections);
  const uniqueCells = [];
  const seen = new Set();
  for (const item of plan.tableCells || []) {
    const key = `${item.sec}:${item.para}:${item.controlIndex || 0}:${item.cellIndex}`;
    if (seen.has(key)) continue;
    seen.add(key);
    uniqueCells.push(item);
  }
  for (const item of uniqueCells) {
    const baseCell = {
      sec: item.sec,
      para: item.para,
      controlIndex: item.controlIndex || 0,
      cellIndex: item.cellIndex,
      cellParaIndex: item.cellParaIndex || 0,
      charOffset: 0,
    };
    try {
      const text = await bridge.getTextInCell(baseCell, 9999);
      cells.push({ ...baseCell, label: item.label || "", text: String(text || "") });
    } catch (_error) {
      cells.push({ ...baseCell, label: item.label || "", text: "" });
    }
  }
  return { paragraphs, cells };
}

function coverValuesFromSections(payload, sections) {
  const project = payload?.project || {};
  const section = (sections || []).find((item) => item.id === "title" || item.id === "cover") || {};
  const lines = String(section.body || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const dateLine = lines.find((line) => /\d{4}\.\s*\d{1,2}/.test(line)) || new Date().toISOString().slice(0, 7).replace("-", ". ");
  const titleLines = lines
    .filter((line) => !/\d{4}\.\s*\d{1,2}/.test(line))
    .filter((line) => !/평가책임자|평가수행기관|KOICA|World Friends/i.test(line))
    .filter((line) => !/^\(?1\)?\s*표지$/.test(line))
    .filter((line) => !/종료평가 결과보고서/.test(line))
    .slice(0, 3);
  const title = titleLines.length
    ? titleLines.join("\n")
    : `${wrapRhwpTitle(project.title || "사업명 확인 중", 24)}\n종료평가 결과보고서`;
  const manager = lines.find((line) => /평가책임자/.test(line)) || "평가책임자/수행기관 확인 중";
  const institution = lines.find((line) => /평가수행기관/.test(line)) || "";
  return { title, dateLine, manager, institution };
}

function ReportEditor({ onClose, autoDraftOnOpen = false, initialMode = "draft" }) {
  const templateMode = initialMode === "template";
  const [payload, setPayload] = useState(null);
  const [sections, setSections] = useState([]);
  const [message, setMessage] = useState(templateMode ? "원본 5-1 양식을 불러오는 중.." : "평가보고서 초안을 불러오는 중..");
  const [rhwpStatus, setRhwpStatus] = useState("rhwp 에디터 준비 중..");
  const [rhwpBridge, setRhwpBridge] = useState(null);
  const [chatMessages, setChatMessages] = useState([
    { role: "assistant", content: "수정할 파트와 요청을 적어주세요. 해당 섹션의 현재 수정본을 기준으로 다시 작성합니다." },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [targetSectionId, setTargetSectionId] = useState("summary");
  const [promptParts, setPromptParts] = useState([]);
  const [reportReferenceDocuments, setReportReferenceDocuments] = useState([]);
  const [sectionSettingsVersion, setSectionSettingsVersion] = useState(1);
  const [sectionSettingsOpen, setSectionSettingsOpen] = useState(false);
  const [referenceSearch, setReferenceSearch] = useState("");
  const [sectionGenerating, setSectionGenerating] = useState(false);
  const [targetPartId, setTargetPartId] = useState("grade");
  const [tocPageMap, setTocPageMap] = useState({});
  const [chatBusy, setChatBusy] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [draftProgress, setDraftProgress] = useState({ active: false, done: 0, total: 0, label: "" });
  const iframeRef = React.useRef(null);
  const autoAppliedRef = React.useRef(false);
  const autoDraftRef = React.useRef(false);
  const activeChatMessages = chatMessages.filter((item) => !item.partId || item.partId === targetPartId);
  const activePromptPart = promptParts.find((part) => part.id === targetPartId) || {};
  const activeReferenceEvidence = activePromptPart.referenceEvidence || {};
  const activeReferenceEvidenceRows = Object.entries(activeReferenceEvidence).flatMap(([criterionId, names]) =>
    (names || []).map((name) => ({ criterionId, name }))
  );

  useEffect(() => {
    api("/api/reports/editor")
      .then((result) => {
        setPayload(result);
        if (templateMode) {
          setSections([]);
          setMessage("저장된 AI 작성본을 초기화하고 원본 5-1 양식을 열었습니다.");
        } else {
          setSections(result.sections || []);
          setMessage(result.source === "saved" ? `저장본 불러옴 - ${result.updatedAt}` : "LLM 초안 생성 완료");
        }
      })
      .catch(() => setMessage("보고서 에디터를 불러오지 못했습니다."));
  }, [templateMode]);

  useEffect(() => {
    api("/api/reports/section-settings")
      .then((result) => {
        const parts = result.editorParts || result.parts || [];
        setPromptParts(parts);
        setReportReferenceDocuments(result.referenceDocuments || []);
        setSectionSettingsVersion(result.version || 1);
        if (parts.length) {
          setTargetPartId(parts[0].id);
          setTargetSectionId(parts[0].sectionId || parts[0].id);
        }
      })
      .catch(() => setPromptParts([]));
  }, []);

  function updatePromptPart(patch) {
    setPromptParts((current) => current.map((part) => part.id === targetPartId ? { ...part, ...patch } : part));
  }

  async function saveSectionSettings() {
    setMessage("섹션별 작성 기준 저장 중..");
    const result = await api("/api/reports/section-settings", { method: "POST", body: { sections: promptParts } });
    setPromptParts(result.editorParts || promptParts);
    setReportReferenceDocuments(result.referenceDocuments || reportReferenceDocuments);
    setSectionSettingsVersion(result.version || sectionSettingsVersion);
    setSectionSettingsOpen(false);
    setMessage(`섹션 작성 기준 v${result.version} 저장 완료`);
  }

  async function generateSelectedSection() {
    if (sectionGenerating || !targetPartId) return;
    setSectionGenerating(true);
    setMessage(`${activePromptPart.title || "선택 섹션"}만 AI로 생성 중..`);
    try {
      const result = await api("/api/reports/editor/auto-draft", { method: "POST", timeoutMs: 120000, body: { sections, partIds: [targetPartId], force: true } });
      setSections(result.sections || sections);
      const generated = (result.results || []).find((item) => item.partId === targetPartId);
      setMessage(generated?.ok ? `${generated.title || activePromptPart.title} 단독 생성·저장 완료` : `${activePromptPart.title || "선택 섹션"} 생성 결과를 확인하세요.`);
      if (rhwpBridge) await loadRhwpExportDraft(rhwpBridge, { saveFirst: false });
    } catch (error) {
      setMessage(`선택 섹션 생성 오류: ${error.message || error}`);
    } finally {
      setSectionGenerating(false);
    }
  }

  useEffect(() => {
    if (templateMode || !autoDraftOnOpen || !payload || !promptParts.length || !sections.length || autoDraftRef.current) return undefined;
    autoDraftRef.current = true;
    let cancelled = false;

    async function generateInitialDrafts() {
      const total = 1;
      setDraftProgress({ active: true, done: 0, total, label: "섹션 1~27 AI 초안 준비" });
      setMessage("임시 안전 모드: 섹션 1~27만 AI로 작성하고 전체 섹션을 생성합니다.");
      setChatMessages((current) => current.filter((item) => !item.autoDraft));
      try {
        const result = await api("/api/reports/editor/auto-draft", {
          method: "POST",
          timeoutMs: 90000,
          body: { sections },
        });
        if (!cancelled) {
          const results = result.results || [];
          setSections(result.sections || sections);
          setChatMessages((current) => [
            ...current.filter((item) => !item.autoDraft),
            ...results.map((item) => ({
              role: "assistant",
              autoDraft: true,
              partId: item.partId,
              sectionId: item.sectionId,
              title: item.title || "",
              content: item.content || "확인 중: AI 초안 결과가 비어 있습니다.",
              canApply: false,
              failed: !item.ok,
            })),
          ]);
          setDraftProgress({ active: false, done: result.total || total, total: result.total || total, label: "완료" });
          setMessage(`섹션 1~27 초안 반영 및 저장 완료 - 성공 ${result.done}/${result.total}, 보완 필요 ${result.failed} - ${result.updatedAt}`);
        }
      } catch (error) {
        if (!cancelled) {
          setDraftProgress({ active: false, done: 0, total, label: "중단" });
          setMessage(`섹션 1~27 초안 생성 중 오류: ${error.message || error}`);
        }
      }
    }

    generateInitialDrafts();
    return () => {
      cancelled = true;
    };
  }, [payload, promptParts, sections.length, templateMode]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return undefined;
    let cancelled = false;
    let bridge = null;

    async function boot() {
      try {
        await new Promise((resolve) => iframe.addEventListener("load", resolve, { once: true }));
        if (cancelled) return;
        bridge = createRhwpBridge(iframe);
        setRhwpStatus("rhwp WASM 초기화 대기 중..");
        await bridge.ready();
        if (cancelled) return;
        const result = templateMode ? await loadRhwpTemplate(bridge) : await loadRhwpExportDraft(bridge);
        if (cancelled) return;
        setRhwpBridge(bridge);
        setRhwpStatus(templateMode ? `원본 5-1 양식 로드 완료 - ${result?.pageCount || "-"}쪽` : `섹션 1~27 HWPX 미리보기 로드 완료 - ${result?.pageCount || "-"}쪽`);
      } catch (error) {
        setRhwpStatus(error.message || "rhwp 에디터를 초기화하지 못했습니다.");
      }
    }

    boot();
    return () => {
      cancelled = true;
      if (bridge) bridge.destroy();
    };
  }, [templateMode]);

  useEffect(() => {
    if (templateMode) return;
    if (!payload || !rhwpBridge || !sections.length || autoAppliedRef.current) return;
    autoAppliedRef.current = true;
    loadRhwpExportDraft(rhwpBridge, { saveFirst: false }).catch((error) => {
      setRhwpStatus(`미리보기 HWPX 초안 로드 중 오류: ${error.message || error}`);
    });
  }, [payload, rhwpBridge, sections.length, templateMode]);

  function updateSection(index, patch) {
    setSections((current) => current.map((section, sectionIndex) =>
      sectionIndex === index ? { ...section, ...patch } : section,
    ));
  }

  async function save() {
    setIsSaving(true);
    setMessage("수정 내용을 저장하는 중..");
    try {
      const result = await api("/api/reports/editor", {
        method: "POST",
        body: { sections },
      });
      setSections(result.sections || sections);
      setMessage(`저장 완료 - ${result.updatedAt}`);
    } finally {
      setIsSaving(false);
    }
  }

  async function saveAndDownload() {
    await save();
    window.location.href = "/api/reports/evaluation-package";
  }

  async function copySection(section) {
    await navigator.clipboard.writeText(section.body || "");
    setMessage(`복사 완료 - ${section.title}`);
  }

  async function copyAllSections() {
    await navigator.clipboard.writeText(reportSectionsToText(sections));
    setMessage("전체 AI 작성본을 클립보드에 복사했습니다.");
  }

  async function sendReportChat() {
    const message = chatInput.trim();
    if (!message || chatBusy) return;
    const targetPart = promptParts.find((part) => part.id === targetPartId);
    const requestSectionId = targetPart?.sectionId || targetSectionId || targetPartId;
    const currentSection = sections.find((item) => item.id === requestSectionId || item.id === targetPartId);
    setChatInput("");
    setChatBusy(true);
    setChatMessages((current) => [
      ...current,
      {
        role: "user",
        partId: targetPartId,
        sectionId: requestSectionId,
        title: targetPart?.title || "",
        content: message,
      },
    ]);
    try {
      const result = await api("/api/reports/editor/chat", {
        method: "POST",
        body: {
          message,
          partId: targetPartId,
          sectionId: requestSectionId,
          section: currentSection || { id: requestSectionId, title: targetPart?.title || "", body: "" },
          sections,
        },
      });
      const revisedContent = result.content || "확인 중: AI 수정 결과가 비어 있습니다.";
      const resolvedSectionId = result.sectionId || requestSectionId;
      const resolvedTitle = result.title || targetPart?.title || sections.find((item) => item.id === resolvedSectionId)?.title || "";
      let found = false;
      let nextSections = sections.map((section) => {
        if (section.id !== resolvedSectionId) return section;
        found = true;
        return { ...section, body: revisedContent };
      });
      if (!found) {
        nextSections = [
          ...nextSections,
          {
            id: resolvedSectionId,
            title: resolvedTitle,
            body: revisedContent,
          },
        ];
      }
      setSections(nextSections);
      setMessage(`${resolvedTitle || "선택 섹션"} AI 수정본 저장 중..`);
      setIsSaving(true);
      const saved = await api("/api/reports/editor", {
        method: "POST",
        body: { sections: nextSections },
      });
      const savedSections = saved.sections || nextSections;
      setSections(savedSections);
      if (rhwpBridge) {
        await loadRhwpExportDraft(rhwpBridge, { saveFirst: false });
      }
      setChatMessages((current) => [
        ...current,
        {
          role: "assistant",
          partId: result.partId || targetPartId,
          sectionId: resolvedSectionId,
          title: resolvedTitle,
          content: revisedContent,
          canApply: false,
          applied: true,
        },
      ]);
      setMessage(`${resolvedTitle || "선택 섹션"} AI 수정본을 적용하고 HWPX 미리보기를 갱신했습니다.`);
    } catch (error) {
      setChatMessages((current) => [
        ...current,
        { role: "assistant", content: error.message || "AI 수정 요청 처리 중 오류가 발생했습니다." },
      ]);
    } finally {
      setIsSaving(false);
      setChatBusy(false);
    }
  }

  async function applyChatRevision(message) {
    const sectionId = message.sectionId || targetSectionId;
    let found = false;
    let nextSections = sections.map((section) => {
      if (section.id !== sectionId) return section;
      found = true;
      return { ...section, body: message.content };
    });
    if (!found) {
      nextSections = [
        ...nextSections,
        {
          id: sectionId,
          title: message.title || promptParts.find((part) => part.id === message.partId)?.title || sectionId,
          body: message.content,
        },
      ];
    }
    setSections(nextSections);
    setMessage(`${message.title || "선택 섹션"} AI 수정본을 적용 중..`);
    setIsSaving(true);
    try {
      const result = await api("/api/reports/editor", {
        method: "POST",
        body: { sections: nextSections },
      });
      const savedSections = result.sections || nextSections;
      setSections(savedSections);
      if (rhwpBridge) {
        await loadRhwpExportDraft(rhwpBridge, { saveFirst: false });
      }
      setMessage(`${message.title || "선택 섹션"} AI 수정본을 적용하고 HWPX 초안을 다시 불러왔습니다.`);
    } catch (error) {
      setMessage(`AI 수정본 적용 중 오류: ${error.message || error}`);
    } finally {
      setIsSaving(false);
    }
  }

  async function selectReportPart(partId, sectionId) {
    setTargetPartId(partId);
    setTargetSectionId(sectionId);
    if (!rhwpBridge) return;
    try {
      const plan = buildRhwpBodyFillPlan(payload, sections);
      const promptPart = promptParts.find((part) => part.id === partId || part.sectionId === sectionId) || {};
      const headingItem = (plan.headingInserts || []).find((item) => item.id === partId || item.id === sectionId);
      const fallbackQueries = [
        promptPart.title,
        String(promptPart.title || "").replace(/^\(\d+\)\s*/, ""),
        sections.find((section) => section.id === sectionId || section.id === partId)?.title,
      ];
      const target = await findReportPartNavigationTarget(rhwpBridge, headingItem || {}, fallbackQueries);
      const fallbackPage = reportPartPageIndex(partId, sectionId, tocPageMap);
      await rhwpBridge.scrollToPage(target?.pageIndex ?? fallbackPage, 21);
      setRhwpStatus(
        target
          ? `선택 파트로 이동했습니다 - ${promptPart.title || sectionId}`
          : `선택 파트 위치를 제목 검색으로 찾지 못해 예상 페이지로 이동했습니다 - ${promptPart.title || sectionId}`
      );
    } catch (_error) {
      // rhwp iframe이 아직 문서를 렌더링 중이면 선택 상태만 갱신한다.
    }
  }

  async function reloadRhwpTemplate() {
    if (!rhwpBridge) {
      setRhwpStatus("rhwp 에디터가 아직 준비되지 않았습니다.");
      return;
    }
    await loadRhwpExportDraft(rhwpBridge, { saveFirst: true });
  }

  async function loadRhwpExportDraft(bridge, options = {}) {
    if (options.saveFirst) {
      await save();
    }
    setRhwpStatus("섹션 1~27 텍스트만 치환한 HWPX를 생성해 rhwp 미리보기로 여는 중..");
    const checked = await api("/api/reports/editor/body-test-hwpx", {
      method: "POST",
      body: {},
    });
    setTocPageMap(checked.tocPageMap || {});
    const bytes = base64ToBytes(checked.data);
    const fileName = checked.fileName || "5-1_종료평가_결과보고서_초안.hwpx";
    const result = await bridge.loadFile(bytes, fileName);
    setRhwpStatus(`섹션 1~27 HWPX 미리보기 로드 완료 - 변경 ${checked.changedSlots || 0}개 - ${checked.sections || 0}개 구역/${checked.pages || result?.pageCount || "-"}쪽`);
    return result;
  }

  async function loadRhwpTemplate(bridge, suffix = "") {
    setRhwpStatus("5-1 원본 HWPX 양식을 다시 불러오는 중..");
    const response = await fetch("/api/reports/template/5-1");
    if (!response.ok) {
      setRhwpStatus("5-1 원본 양식을 다시 불러오지 못했습니다.");
      return;
    }
    const buffer = await response.arrayBuffer();
    const contentType = response.headers.get("content-type") || "";
    const templateName = decodeURIComponent(response.headers.get("x-template-file") || "");
    const fileName = templateName || (contentType.includes("zip") ? "5-1. 종료평가 결과보고서 placeholder.hwpx" : "5-1. 종료평가 결과보고서 양식.hwp");
    const result = await bridge.loadFile(buffer, fileName);
    setRhwpStatus(`원본 5-1 양식 ${suffix ? `${suffix} ` : ""}로드 완료 - ${result?.pageCount || "-"}쪽`);
    return result;
  }

  async function applyDraftToRhwp() {
    setRhwpStatus("임시 안전 모드에서는 rhwp 직접 치환을 사용하지 않습니다. 서버가 만든 섹션 1~27 HWPX만 미리보기로 엽니다.");
    return;
    if (!rhwpBridge) {
      setRhwpStatus("rhwp 에디터가 아직 준비되지 않았습니다.");
      return;
    }
    const plan = buildRhwpAutoFillPlan(payload);
    setRhwpStatus("원본 HWP 양식의 표지와 필드만 안전하게 반영 중..");
    await save();

    let changedCount = 0;
    for (const [name, value] of plan.fields) {
      try {
        const changed = await rhwpBridge.setFieldValueByName(name, value);
        if (changed) changedCount += 1;
      } catch (_error) {
        // 필드가 없는 양식이면 본문 치환 단계에서 처리한다.
      }
    }
    for (const [query, value] of plan.placeholders) {
      try {
        const changed = await rhwpBridge.replaceAll(query, value);
        if (changed) changedCount += Number(changed) || 1;
      } catch (_error) {
        // 양식 버전에 따라 placeholder가 다를 수 있다.
      }
    }

    setRhwpStatus(`표지/필드 반영 완료 - ${changedCount}개 위치 수정 - 본문은 오른쪽 초안을 확인해 직접 붙여넣어 주세요.`);
  }

  async function applyCoverToRhwp(nextSections = sections) {
    setRhwpStatus("임시 안전 모드에서는 rhwp 직접 치환을 사용하지 않습니다. 서버가 만든 섹션 1~27 HWPX만 미리보기로 엽니다.");
    return;
    if (!rhwpBridge) {
      setRhwpStatus("rhwp 에디터가 아직 준비되지 않았습니다.");
      return;
    }
    setRhwpStatus("현재 문서의 표지 영역만 반영 중..");
    const values = coverValuesFromSections(payload, nextSections);
    const replacements = [
      ["{사업이름}", values.title],
      ["〇〇사업 종료평가 결과보고서", values.title],
      ["〇〇사업 종료평가", values.title.replace(/\n?종료평가 결과보고서\s*$/g, "\n종료평가")],
      ["2023. 12", values.dateLine],
      ["평가책임자 OOO", values.manager],
      ["평가수행기관 OOO(로고)", values.institution],
    ];
    let changedCount = 0;
    for (const [query, value] of replacements) {
      try {
        const changed = await rhwpBridge.replaceAll(query, value);
        if (changed) changedCount += Number(changed) || 1;
      } catch (_error) {
        // 표지 양식 자리표시자가 다르면 해당 항목만 건너뛴다.
      }
    }
    await applyCoverTitleFit(rhwpBridge, values.title);
    setRhwpStatus(`표지 반영 완료 - ${changedCount}개 표지 항목 수정 - 다른 파트는 변경하지 않았습니다.`);
  }

  async function applyGradeTableToRhwp(nextSections = sections, options = {}) {
    setRhwpStatus("임시 안전 모드에서는 서버가 검증한 표 기준으로 섹션 1~27만 치환합니다.");
    return;
    if (!rhwpBridge) {
      setRhwpStatus("rhwp 에디터가 아직 준비되지 않았습니다.");
      return;
    }
    setRhwpStatus(options.reload ? "원본 5-1 양식에 평가 등급 결과표만 반영 중.." : "현재 문서에 평가 등급 결과표만 반영 중..");
    if (options.reload) {
      await loadRhwpTemplate(rhwpBridge, "다시");
    }
    const cells = buildRhwpGradeTableCells(payload, nextSections);
    let changedCount = 0;
    for (const item of cells) {
      try {
        await replaceTableCellText(rhwpBridge, item, item.text);
        changedCount += 1;
      } catch (_error) {
        // 표 좌표가 양식 버전과 다르면 해당 셀만 건너뛰고 계속 확인한다.
      }
    }
    const cleanupTexts = [
      "본 평가는 주어진 평가표에 근거하여 종합 평가 등급과 점수를 모두 제시해야 함",
      "구간별 점수 산정 참고 사항은 별도 작성파일 참조 요망.",
      "적절성(Relevance) - 1~4점",
      "일관성(Coherence) - 1~4점",
      "효과성(Effectiveness) - 1~4점",
      "효율성(Efficiency) - 1~4점",
      "지속가능성(Sustainability) - 1~4점",
      "적절성(Relevance)",
      "일관성(Coherence)",
      "효과성(Effectiveness)",
      "효율성(Efficiency)",
      "지속가능성(Sustainability)",
      "평가의견:",
      "적용근거:",
      "보완 필요사항:",
      "평가대상 사업명",
      "평가대상 사업명:",
      "종합점수:",
      "종합점수 :",
      "KOICA 평가등급:",
      "KOICA 평가등급 :",
      "국무조정실 평가등급:",
      "국무조정실 평가등급 :",
      "점수 산정근거: 업로드 증빙, 기준별 평가의견, 전략자료 현황을 종합하여 산정함",
    ];
    let cleanupCount = 0;
    for (const text of cleanupTexts) {
      try {
        const changed = await rhwpBridge.replaceAll(text, "");
        cleanupCount += Number(changed) || 0;
      } catch (_error) {
        // 양식 버전별 안내문 위치가 다르면 제거만 건너뛴다.
      }
    }
    setRhwpStatus(`평가 등급 결과표 반영 완료 - ${changedCount}/${cells.length}개 셀 수정 - 안내문 ${cleanupCount}건 제거 - HWPX 저장 버튼으로 다운로드하세요.`);
  }

  async function applyBodyToRhwp(options = {}) {
    setRhwpStatus("임시 안전 모드에서는 rhwp 직접 본문 반영을 사용하지 않습니다. 섹션 1~27만 서버에서 텍스트 치환합니다.");
    return;
    if (!rhwpBridge) {
      setRhwpStatus("rhwp 에디터가 아직 준비되지 않았습니다.");
      return;
    }
    const plan = buildRhwpBodyFillPlan(payload, sections);
    const appliedPartIds = new Set();
    const markPartApplied = (partId) => {
      if (partId && plan.partIds.includes(partId)) {
        appliedPartIds.add(partId);
      }
    };
    setRhwpStatus("원본 5-1 양식에 AI 작성 내용과 사업 데이터를 자동 반영 중..");
    if (!options.silentSave) {
      await save();
    }
    await loadRhwpTemplate(rhwpBridge, "다시");

    const coverPlan = buildRhwpAutoFillPlan(payload);
    for (const [query, value] of coverPlan.placeholders) {
      try {
        await rhwpBridge.replaceAll(query, value);
      } catch (_error) {
        // 양식 버전에 따라 placeholder가 다를 수 있다.
      }
    }
    await applyCoverTitleFit(rhwpBridge, coverPlan.wrappedTitle);

    markPartApplied("cover");

    const rawFields = await rhwpBridge.getFieldList();
    const fields = normalizeRhwpFieldList(rawFields);
    if (fields.length < 11) {
      setRhwpStatus(`필드 ${fields.length}개 확인 - 임시 안전 모드에서는 섹션 1~27 본문 반영을 중단합니다.`);
    }

    let changedCount = 0;
    for (const item of plan.deleteControls || []) {
      try {
        if (item.type === "picture") {
          await rhwpBridge.deletePictureControl(item);
        } else {
          await rhwpBridge.deleteShapeControl(item);
        }
        changedCount += 1;
      } catch (_error) {
        // 예시 도형/이미지가 없는 양식이면 그대로 진행한다.
      }
    }

    for (const item of plan.guideCleanups || []) {
      try {
        await rhwpBridge.replaceText({
          sec: item.sec,
          para: item.para,
          charOffset: item.charOffset || 0,
          length: item.length || 0,
        }, item.text || "");
        changedCount += 1;
      } catch (_error) {
        try {
          if (item.query) {
            const changed = await rhwpBridge.replaceAll(item.query, item.text || "");
            if (changed) changedCount += Number(changed) || 1;
          }
        } catch (_ignored) {
          // 안내 문단 좌표와 원문이 모두 다른 양식이면 해당 영역은 건너뛴다.
        }
      }
    }

    for (const item of plan.headingInserts || []) {
      try {
        const changed = await replaceHeadingWithBody(rhwpBridge, item);
        if (changed) {
          changedCount += 1;
          markPartApplied(item.id);
          if (item.id === "summary") markPartApplied("summary-ko");
        }
      } catch (_error) {
        // Keep applying the remaining report parts even if one heading is not found.
      }
    }

    plan.headingInserts = [];

    for (const item of plan.paragraphInserts) {
      if (item.id && appliedPartIds.has(item.id)) continue;
      try {
        await rhwpBridge.replaceText({
          sec: item.sec,
          para: item.para,
          charOffset: 0,
          length: 0,
        }, item.text);
        changedCount += 1;
        markPartApplied(item.id);
      } catch (_error) {
        // 섹션/문단 좌표가 다른 양식이면 해당 영역은 건너뛴다.
      }
    }

    for (const item of plan.fieldInserts) {
      try {
        const field = fields[item.fieldOrder];
        if (!field) continue;
        const fieldId = fieldIdentifier(field, item.fieldOrder);
        const changed = await rhwpBridge.setFieldValue(fieldId, item.text);
        if (changed) changedCount += 1;
      } catch (_error) {
        // 개별 필드 실패가 나머지 작성영역 반영을 막지 않는다.
      }
    }

    for (const item of plan.headingInserts || []) {
      try {
        const changed = await replaceHeadingWithBody(rhwpBridge, item);
        if (changed) changedCount += 1;
      } catch (_error) {
        // 제목 검색 기반 반영이 실패해도 표지 다른 작성영역 반영은 계속한다.
      }
    }

    for (const item of plan.tableCells) {
      try {
        await replaceTableCellText(rhwpBridge, item, item.text);
        changedCount += 1;
        markPartApplied(inferTableCellPartId(item));
      } catch (_error) {
        // 표 구조가 다른 양식이면 해당 셀은 건너뛴다.
      }
    }

    for (const item of plan.residualReplacements || []) {
      try {
        const changed = await rhwpBridge.replaceAll(item.query, item.text || "");
        if (changed) changedCount += Number(changed) || 1;
      } catch (_error) {
        // 전체 정리 함수는 남은 안내 문구가 있을 때만 적용한다.
      }
    }

    const missingPartIds = plan.partIds.filter((partId) => !appliedPartIds.has(partId));
    const missingText = missingPartIds.length ? ` - 미반영 확인 필요: ${missingPartIds.join(", ")}` : "";
    setRhwpStatus(`AI 초안 반영 완료 - 임시 안전 모드에서는 섹션 1~27 본문 반영을 서버 HWPX 생성으로 처리합니다. ${changedCount}개 작성 영역 반영${missingText}`);
  }

  async function exportRhwpHwpx() {
    const projectName = (payload?.project?.title || "ODA_사업").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 80);
    try {
      if (templateMode) {
        if (!rhwpBridge) {
          setRhwpStatus("rhwp 에디터가 아직 준비되지 않았습니다.");
          return;
        }
        setRhwpStatus("현재 열린 원본 양식을 그대로 HWPX로 저장하는 중..");
        const finalBytes = await rhwpBridge.exportHwpx();
        downloadBytes(finalBytes, "5-1_원본양식_종료평가_결과보고서.hwpx", "application/x-hwp+zip");
        setRhwpStatus(`원본 양식 HWPX 저장 완료 - ${finalBytes.length} bytes`);
        return;
      }
      setRhwpStatus("섹션 1~27 텍스트를 원본 HWPX에 치환한 저장 파일을 만드는 중..");
      await save();
      const checked = await api("/api/reports/editor/body-test-hwpx", {
        method: "POST",
        body: {},
      });
      downloadDirect("/api/reports/editor/body-test-hwpx/download");
      setRhwpStatus(`HWPX \uC800\uC7A5 \uC694\uCCAD \uC644\uB8CC - \uBCF4\uACE0\uC11C \uC139\uC158 1~27 ${checked.changedSlots || 0}\uAC1C \uCE58\uD658 - HWPX \uB0B4\uBD80 \uAD6C\uC5ED ${checked.sections || 0}\uAC1C/${checked.pages || 0}\uCABD - ${checked.bytes || 0} bytes`);
    } catch (error) {
      setRhwpStatus(`HWPX 저장 실패: ${error.message || error}`);
    }
  }

  async function downloadCoverChangedHwpxTemplate() {
    return exportRhwpHwpx();
    try {
      setRhwpStatus("원본 HWPX 양식에서 섹션 1~27만 변경해 다운로드 중..");
      const checked = await api("/api/reports/editor/cover-hwpx", { method: "POST" });
      const finalBytes = base64ToBytes(checked.data);
      downloadBytes(finalBytes, checked.fileName || "5-1_표지변경_종료평가_결과보고서.hwpx", "application/x-hwp+zip");
      setRhwpStatus(`표지 변경 다운로드 완료 - ${checked.sections || 0}개 구역/${checked.pages || 0}쪽 - ${checked.bytes || finalBytes.length} bytes`);
    } catch (error) {
      setRhwpStatus(`표지 변경 다운로드 실패: ${error.message || error}`);
    }
  }

  async function downloadCoverGradeChangedHwpxTemplate() {
    return exportRhwpHwpx();
    try {
      setRhwpStatus("표지와 평가 등급 결과표만 변경해 다운로드 중..");
      const checked = await api("/api/reports/editor/cover-grade-hwpx", { method: "POST" });
      const finalBytes = base64ToBytes(checked.data);
      downloadBytes(finalBytes, checked.fileName || "5-1_표지_평가등급표변경_종료평가_결과보고서.hwpx", "application/x-hwp+zip");
      setRhwpStatus(`표지+평가등급표 다운로드 완료 - ${checked.sections || 0}개 구역/${checked.pages || 0}쪽 - ${checked.bytes || finalBytes.length} bytes`);
    } catch (error) {
      setRhwpStatus(`표지+평가등급표 다운로드 실패: ${error.message || error}`);
    }
  }

  async function downloadBodyTestHwpxTemplate() {
    return exportRhwpHwpx();
    try {
      setRhwpStatus("본문 치환 테스트 파일 다운로드 중..");
      const checked = await api("/api/reports/editor/body-test-hwpx", { method: "POST" });
      const finalBytes = base64ToBytes(checked.data);
      downloadBytes(finalBytes, checked.fileName || "5-1_본문치환테스트_종료평가_결과보고서.hwpx", "application/x-hwp+zip");
      setRhwpStatus(`본문 치환 테스트 다운로드 완료 - ${checked.sections || 0}개 구역/${checked.pages || 0}쪽 - ${checked.bytes || finalBytes.length} bytes`);
    } catch (error) {
      setRhwpStatus(`본문 치환 테스트 다운로드 실패: ${error.message || error}`);
    }
  }

  useEffect(() => {
    const handler = () => {
      exportRhwpHwpx();
    };
    const keyHandler = (event) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && (event.key || "").toLowerCase() === "s") {
        event.preventDefault();
        event.stopPropagation();
        exportRhwpHwpx();
      }
    };
    window.addEventListener("rhwp-safe-save-request", handler);
    window.addEventListener("keydown", keyHandler, true);
    return () => {
      window.removeEventListener("rhwp-safe-save-request", handler);
      window.removeEventListener("keydown", keyHandler, true);
    };
  }, [rhwpBridge, payload, sections]);

  return (
    <div className="preview-backdrop report-editor-backdrop" role="dialog" aria-modal="true" aria-label="평가보고서 작성 에디터">
      <section className="preview-panel report-editor-panel">
        <div className="preview-head">
          <div>
            <p>5-1 종료평가 결과보고서</p>
            <h2>{payload?.project?.title || "평가보고서 작성"}</h2>
            <span>{rhwpStatus}</span>
          </div>
          <button type="button" onClick={onClose}>닫기</button>
        </div>
        <div className="editor-toolbar">
          <div className="editor-status">
            <span className={`status-dot ${draftProgress.active || isSaving || chatBusy ? "active" : ""}`} aria-hidden="true"></span>
            <p>{message}</p>
            {(draftProgress.active || isSaving || chatBusy) && (
              <div className="editor-progress" aria-label="보고서 작성 진행률">
                <span
                  style={{
                    width: `${draftProgress.active && draftProgress.total ? Math.round((draftProgress.done / draftProgress.total) * 100) : 100}%`,
                  }}
                />
              </div>
            )}
            {draftProgress.active && (
              <small>{draftProgress.done}/{draftProgress.total} - {draftProgress.label}</small>
            )}
            {isSaving && !draftProgress.active && <small>저장 중..</small>}
            {chatBusy && !draftProgress.active && <small>AI 수정안 작성 중..</small>}
          </div>
          <div className="editor-toolbar-actions">
            <button type="button" className="overview-link" onClick={exportRhwpHwpx}>HWPX 저장</button>
          </div>
        </div>
        <div className="rhwp-editor-layout">
          <div className="rhwp-frame-wrap">
            <iframe
              ref={iframeRef}
              title="rhwp 5-1 종료평가 결과보고서 에디터"
              src="/assets/rhwp/index.html?autofix=1"
              allow="clipboard-read; clipboard-write"
            />
          </div>
          <aside className="report-ai-panel">
            <div className="report-ai-head">
              <strong>AI 수정 요청</strong>
              <div>
                <button type="button" onClick={() => setSectionSettingsOpen(true)}>섹션 작성 설정</button>
                <button type="button" className="generate-section-button" onClick={generateSelectedSection} disabled={sectionGenerating}>{sectionGenerating ? "생성 중" : "이 섹션만 생성"}</button>
              </div>
            </div>
            <div className="report-reference-box">
              <strong>이 파트 참고 문서</strong>
              {activeReferenceEvidenceRows.length ? (
                <ul>
                  {activeReferenceEvidenceRows.slice(0, 8).map((item) => (
                    <li key={`${item.criterionId}-${item.name}`}>
                      <span>{item.criterionId}</span>
                      {item.name}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>{(activePromptPart.referenceNotes || []).join(" - ") || "원본 양식과 공통 참고자료를 사용합니다."}</p>
              )}
              {activeReferenceEvidenceRows.length > 8 && <p>외 {activeReferenceEvidenceRows.length - 8}개 더 있음</p>}
            </div>
            <div className="report-part-tabs" role="tablist" aria-label="보고서 작성 파트">
              {(promptParts.length ? promptParts : sections).map((part) => {
                const partId = part.id;
                const sectionId = part.sectionId || part.id;
                const active = partId === targetPartId || (!promptParts.length && sectionId === targetSectionId);
                return (
                  <button
                    key={partId}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    className={active ? "active" : ""}
                    onClick={() => {
                      selectReportPart(partId, sectionId);
                    }}
                  >
                    {part.title}
                  </button>
                );
              })}
            </div>
            <div className="report-ai-messages">
              {activeChatMessages.map((item, index) => (
                <article className={`report-ai-message ${item.role}`} key={`${item.role}-${index}`}>
                  {item.title && <strong>{item.title}</strong>}
                  <p>{item.content}</p>
                  {item.canApply && (
                    <button type="button" onClick={() => applyChatRevision(item)}>수정안 적용</button>
                  )}
                </article>
              ))}
            </div>
            <div className="report-ai-input">
              <textarea
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                placeholder="예: 결론을 평가보고서 문체로 정리하고, 부족한 자료는 항목별로 표시해줘."
              />
              <button type="button" onClick={sendReportChat} disabled={chatBusy || !chatInput.trim()}>
                {chatBusy ? "작성 중" : "보내기"}
              </button>
            </div>
            {sectionSettingsOpen && (
              <div className="section-settings-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSectionSettingsOpen(false); }}>
                <section className="section-settings-modal" role="dialog" aria-modal="true" aria-label="섹션별 작성 설정">
                  <header><div><p>SECTION CONTROL · v{sectionSettingsVersion}</p><h2>{activePromptPart.title || "섹션 작성 설정"}</h2><span>작성 로직과 참고자료를 담당자가 직접 관리합니다.</span></div><button type="button" onClick={() => setSectionSettingsOpen(false)}>닫기</button></header>
                  <div className="section-settings-layout">
                    <nav>{promptParts.map((part) => <button type="button" className={part.id === targetPartId ? "active" : ""} key={part.id} onClick={() => { setTargetPartId(part.id); setTargetSectionId(part.sectionId || part.id); }}>{part.title}</button>)}</nav>
                    <div className="section-settings-form">
                      <label>섹션 작성 목적<textarea value={activePromptPart.description || ""} onChange={(e) => updatePromptPart({description:e.target.value})}/></label>
                      <label>기본 생성 프롬프트<textarea className="prompt-editor" value={activePromptPart.prompt || ""} onChange={(e) => updatePromptPart({prompt:e.target.value})}/></label>
                      <label>담당자 추가 지침<textarea value={activePromptPart.additionalInstructions || ""} placeholder="예: 파푸아 7개 지역별 편차를 별도 문단으로 비교한다." onChange={(e) => updatePromptPart({additionalInstructions:e.target.value})}/></label>
                      <section className="section-reference-picker"><header><div><strong>이 섹션에서 참고할 자료</strong><span>{(activePromptPart.customReferenceDocumentIds || []).length}개 선택</span></div><input placeholder="파일명·자료 슬롯 검색" value={referenceSearch} onChange={(e) => setReferenceSearch(e.target.value)}/></header><div>{reportReferenceDocuments.filter((doc) => `${doc.fileName} ${doc.evidenceName} ${doc.criterionId}`.toLowerCase().includes(referenceSearch.toLowerCase())).map((doc) => { const selected=(activePromptPart.customReferenceDocumentIds || []).includes(doc.id); return <label key={doc.id} className={selected ? "selected" : ""}><input type="checkbox" checked={selected} onChange={(e) => { const current=activePromptPart.customReferenceDocumentIds || []; updatePromptPart({customReferenceDocumentIds:e.target.checked ? [...current,doc.id] : current.filter((id)=>id!==doc.id)}); }}/><span><strong>{doc.fileName}</strong><small>{doc.criterionId} · {doc.evidenceName}</small></span></label>; })}</div></section>
                    </div>
                  </div>
                  <footer><span>저장한 설정은 다음 섹션 생성부터 적용됩니다.</span><button type="button" onClick={saveSectionSettings}>전체 섹션 설정 저장</button></footer>
                </section>
              </div>
            )}
          </aside>
        </div>
      </section>
    </div>
  );
}

function ReportGenerationConfirm({ data, onCancel, onContinue, onFreshStart, onOpenTemplate }) {
  const projectReady = Boolean(data?.project?.overviewReady);
  const evidence = data?.insights?.evidence || {};
  const readiness = data?.insights?.readiness || {};
  const report = data?.insights?.report || {};
  const missingCount = data?.insights?.missingEvidence?.length || 0;
  const hasSavedReport = Boolean(report.saved || report.updatedAt || (report.sections || 0) > 0);

  return (
    <div className="report-confirm-backdrop" role="dialog" aria-modal="true" aria-label="평가보고서 작성 확인">
      <section className="report-confirm-panel">
        <header>
          <p>AI 보고서 생성 확인</p>
          <h2>평가보고서 작성 방식을 선택해 주세요</h2>
        </header>
        <div className="report-confirm-body">
          <p>
            저장된 보고서가 있으면 이어서 열고, 새로 작성하면 섹션 1~27을 다시 AI 요청으로 생성합니다.
          </p>
          <dl>
            <div>
              <dt>저장본</dt>
              <dd className={hasSavedReport ? "ok" : "warn"}>{hasSavedReport ? "섹션 1~27 저장본 " + (report.sections || 0) + "개" : "없음"}</dd>
            </div>
            <div>
              <dt>마지막 업데이트</dt>
              <dd>{report.updatedAt || "기록 없음"}</dd>
            </div>
            <div>
              <dt>사업개요</dt>
              <dd className={projectReady ? "ok" : "warn"}>{projectReady ? "등록됨" : "미등록"}</dd>
            </div>
            <div>
              <dt>필수 증빙</dt>
              <dd>{evidence.uploaded || 0}/{evidence.required || 0}</dd>
            </div>
            <div>
              <dt>증빙 확보</dt>
              <dd>{readiness.evidenceRate || 0}%</dd>
            </div>
            <div>
              <dt>우선 보완</dt>
              <dd className={missingCount ? "warn" : "ok"}>{missingCount}</dd>
            </div>
          </dl>
          <div className="report-confirm-note">
            <strong>진행 전 확인</strong>
            <span>사업개요서, PDM, 성과자료, 예산 및 운영자료, 인터뷰 현장자료를 가능한 한 먼저 넣어주세요.</span>
            <span>자료가 부족한 항목은 확인 필요 자료를 표시하고 보수적으로 작성합니다.</span>
            <span>원본 양식 열기는 저장된 AI 작성본을 초기화하고 원본 HWPX 양식을 에디터에 엽니다.</span>
          </div>
        </div>
        <footer>
          <button type="button" className="overview-link secondary" onClick={onCancel}>취소</button>
          <button type="button" className="overview-link secondary" onClick={onContinue} disabled={!hasSavedReport}>이어서 작성하기</button>
          <button type="button" className="overview-link report-link" onClick={onFreshStart}>새로 작성하기</button>
          <button type="button" className="overview-link secondary" onClick={onOpenTemplate}>원본 양식 열기</button>
        </footer>
      </section>
    </div>
  );
}

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("화면 렌더링 오류", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="loading-screen">
          <strong>화면 렌더링 오류</strong>
          <span>{this.state.error?.message || String(this.state.error)}</span>
        </main>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [data, setData] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [view, setView] = useState("dashboard");
  const [detailBackView, setDetailBackView] = useState("dashboard");
  const [highlightReferenceKey, setHighlightReferenceKey] = useState(null);
  const [reportEditorOpen, setReportEditorOpen] = useState(false);
  const [reportConfirmOpen, setReportConfirmOpen] = useState(false);
  const [reportPreparing, setReportPreparing] = useState(false);
  const [reportPrepareMessage, setReportPrepareMessage] = useState("");
  const [reportEditorAutoDraft, setReportEditorAutoDraft] = useState(false);
  const [reportEditorMode, setReportEditorMode] = useState("draft");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const referenceDocuments = useMemo(
    () => buildReferenceDocuments(data?.criteria || []),
    [data],
  );
  const selectedCriterion = useMemo(
    () => (view === "detail" ? data?.criteria.find((item) => item.id === selectedId) : null),
    [data, selectedId, view],
  );

  function openReference(referenceKey = null) {
    setHighlightReferenceKey(referenceKey);
    setSelectedId(null);
    setDetailBackView("dashboard");
    setView("references");
  }

  useEffect(() => {
    api("/api/dashboard")
      .then(setData)
      .catch((error) => {
        setData({
          project: { title: "대시보드 로드 오류", period: "-", budget: "-" },
          criteria: [],
          insights: {},
          loadError: error.message || String(error),
        });
      });
  }, [loadAttempt]);

  async function requestReportEditor() {
    if (reportPreparing) return;
    try {
      const refreshed = await api("/api/dashboard");
      setData(refreshed);
    } catch (error) {
      console.warn("보고서 저장 상태 갱신 실패", error);
    }
    setReportConfirmOpen(true);
  }

  async function openOriginalReportTemplate() {
    if (reportPreparing) return;
    setReportConfirmOpen(false);
    setReportPreparing(true);
    setReportPrepareMessage("저장된 AI 작성본을 초기화하고 원본 5-1 양식을 여는 중..");
    try {
      await api("/api/reports/editor/reset-template", {
        method: "POST",
        body: {},
      });
      setReportEditorAutoDraft(false);
      setReportEditorMode("template");
      setReportEditorOpen(true);
      setReportPrepareMessage("원본 양식 로드 준비 완료");
      api("/api/dashboard").then(setData).catch(() => {});
      window.setTimeout(() => setReportPrepareMessage(""), 2000);
    } catch (error) {
      setReportPrepareMessage("원본 양식 초기화 중 오류: " + (error.message || error));
      window.setTimeout(() => setReportPrepareMessage(""), 5000);
    } finally {
      setReportPreparing(false);
    }
  }

  async function openReportEditor(mode = "continue") {
    if (reportPreparing) return;
    setReportConfirmOpen(false);
    setReportEditorMode("draft");
    if (mode === "continue") {
      const updatedAt = data?.insights?.report?.updatedAt;
      setReportPrepareMessage(updatedAt ? "마지막 업데이트 기준으로 불러오는 중 - " + updatedAt : "저장된 보고서를 불러오는 중..");
      setReportEditorAutoDraft(false);
      setReportEditorOpen(true);
      window.setTimeout(() => setReportPrepareMessage(""), 2000);
      return;
    }
    setReportPreparing(true);
    setReportPrepareMessage("임시 안전 모드: 이전 생성 기록을 무시하고 섹션 1~27만 새로 작성하는 중..");
    try {
      setReportPrepareMessage("섹션 1~27 전용 프롬프트로 새로 요청하는 중..");
      const prepared = await api("/api/reports/editor/auto-draft", {
        method: "POST",
        timeoutMs: 120000,
        body: { force: true, reset: true },
      });
      setReportPrepareMessage("섹션 1~27 초안 생성 완료 - 갱신 " + (prepared.generated || 0) + "개 - 재사용 " + (prepared.skipped || 0) + "개");
      setReportEditorAutoDraft(false);
      setReportEditorOpen(true);
      api("/api/dashboard").then(setData).catch(() => {});
    } catch (error) {
      setReportPrepareMessage("보고서 준비 중 오류: " + (error.message || error));
      window.setTimeout(() => setReportPrepareMessage(""), 5000);
    } finally {
      setReportPreparing(false);
    }
  }

  if (!data) {
    return (
      <main className="loading-screen">
        <span className="loading-brand">IO</span>
        <strong>ImpactOps AI</strong>
        <span>성과관리 워크스페이스를 안전하게 불러오는 중입니다.</span>
      </main>
    );
  }

  if (data.loadError) {
    return (
      <main className="load-error-screen" role="alert">
        <span className="load-error-icon" aria-hidden="true">!</span>
        <p>WORKSPACE CONNECTION</p>
        <h1>성과관리 데이터를 불러오지 못했습니다</h1>
        <span>{data.loadError}</span>
        <button type="button" onClick={() => { setData(null); setLoadAttempt((value) => value + 1); }}>
          다시 연결
        </button>
      </main>
    );
  }

  return (
    <>
      {selectedCriterion ? (
        <DetailPage
          criterion={selectedCriterion}
          references={referenceDocuments}
          onBack={() => {
            setSelectedId(null);
            setView(detailBackView);
          }}
          onDashboardUpdate={setData}
          onOpenReference={openReference}
        />
      ) : view === "references" ? (
        <ReferenceListPage
          data={data}
          documents={referenceDocuments}
          highlightKey={highlightReferenceKey}
          onDashboardUpdate={setData}
          onBack={() => setView("dashboard")}
        />
      ) : view === "criteria" ? (
        <CriteriaPage
          data={data}
          onBack={() => setView("dashboard")}
          onSelect={(id) => {
            setSelectedId(id);
            setHighlightReferenceKey(null);
            setDetailBackView("criteria");
            setView("detail");
          }}
          onOpenReferences={() => openReference(null)}
          onOpenReportEditor={requestReportEditor}
        />
      ) : (
        <Dashboard
          data={data}
          onSelect={(id) => {
            setSelectedId(id);
            setHighlightReferenceKey(null);
            setDetailBackView("dashboard");
            setView("detail");
          }}
          onOpenReferences={() => openReference(null)}
          onOpenCriteria={() => setView("criteria")}
          onOpenReportEditor={requestReportEditor}
          onProjectUpdate={(project, dashboard) => setData((current) => dashboard || { ...current, project })}
        />
      )}
      {reportConfirmOpen && (
        <ReportGenerationConfirm
          data={data}
          onCancel={() => setReportConfirmOpen(false)}
          onContinue={() => openReportEditor("continue")}
          onFreshStart={() => openReportEditor("fresh")}
          onOpenTemplate={openOriginalReportTemplate}
        />
      )}
      {reportPreparing && (
        <div className="report-preparing-overlay" role="alert" aria-live="assertive">
          <div>
            <span className="report-spinner" aria-hidden="true"></span>
            <strong>평가보고서 초안 준비</strong>
            <p>{reportPrepareMessage || "관련 문서와 프롬프트 캐시를 확인하고 있습니다."}</p>
          </div>
        </div>
      )}
      {reportEditorOpen && <ReportEditor onClose={() => setReportEditorOpen(false)} autoDraftOnOpen={reportEditorAutoDraft} initialMode={reportEditorMode} />}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
