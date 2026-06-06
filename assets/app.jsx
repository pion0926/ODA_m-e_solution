const { useEffect, useMemo, useState } = React;

function api(path, options = {}) {
  return fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  }).then((response) => {
    if (!response.ok) throw new Error(`API ${path} failed with ${response.status}`);
    return response.json();
  });
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
    .replace(/[()[\]{}·,_\-~'":/\\]/g, " ")
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
  if (/^\[.+\]$/.test(line) || /^(예상점수|예상 점수|핵심사유|증빙공백|점수)/.test(normalizedLine)) return [];
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
  const radius = 192;
  const levels = [0.25, 0.5, 0.75, 1];

  return (
    <article className="radar-card">
      <div className="chart-head">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <span>Radar View</span>
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
            className="radar-area"
            style={{ "--series-color": item.color }}
          />
        ))}
        {criteria.map((item, index) => {
          const [x, y] = polarPoint(cx, cy, radius + 36, index, criteria.length);
          const score = item.currentScore4 || 1;
          const [dotX, dotY] = polarPoint(cx, cy, radius * (score / 4), index, criteria.length);
          return (
            <g key={item.id} className="radar-node" onClick={() => onSelect(item.id)} tabIndex="0" role="button">
              <circle cx={dotX} cy={dotY} r="7" />
              <text x={x} y={y} textAnchor="middle">
                <tspan x={x} dy="0">{item.name}</tspan>
                <tspan x={x} dy="18">{score}점</tspan>
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
    </article>
  );
}

function Dashboard({ data, onSelect, onProjectUpdate, onOpenReferences }) {
  const [preview, setPreview] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  async function openOverview() {
    const result = await api(data.project.overviewPreviewUrl);
    setPreview(result);
    setPreviewOpen(true);
  }

  return (
    <main className="dashboard-main">
      <section className="dashboard-panel" aria-label="M&E Dashboard">
        <div className="project-bar">
          <div>
            <p>사업제목</p>
            <h1>{data.project.title}</h1>
            <span>{data.project.period} / {data.project.budget}</span>
          </div>
          <div className="project-actions">
            <button className="overview-link" type="button" onClick={openOverview}>
              사업개요서 보기
            </button>
            <button className="overview-link secondary" type="button" onClick={onOpenReferences}>
              참고문헌 목록
            </button>
            <a className="overview-link report-link" href="/api/reports/evaluation-package" download>
              평가보고서 작성
            </a>
          </div>
        </div>
        <div className="panel-title">
          <div>
            <p>M&E Dashboard</p>
            <h2>DAC 6 Criteria · Health Monitoring</h2>
          </div>
          <small>Updated {data.updatedAt}</small>
        </div>
        <div className="overall-strip">
          <article>
            <span>종합점수</span>
            <strong>{data.overall.score}/{data.overall.maxScore}점</strong>
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
        <div className="radar-layout">
          <RadarChart
            title={data.chartA.title}
            description={data.chartA.description}
            criteria={data.criteria}
            series={data.chartA.series}
            onSelect={onSelect}
          />
          <RadarChart
            title={data.chartB.title}
            description={data.chartB.description}
            criteria={data.criteria}
            series={data.chartB.series}
            onSelect={onSelect}
          />
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
  useEffect(() => {
    if (!highlightKey) return;
    const target = document.getElementById(`reference-${highlightKey}`);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightKey, documents]);

  const totalSize = documents.reduce((sum, document) => sum + (document.size || 0), 0);
  const unmatchedDocuments = data.unmatchedDocuments || [];
  const pendingDocuments = batchProposals.length ? batchProposals : data.pendingDocuments || [];

  async function uploadBatch(files) {
    const fileList = Array.from(files || []);
    if (!fileList.length) return;
    setBatchMessage(`${fileList.length}개 문서 분류 제안 생성 중...`);
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
    setBatchMessage(`분류 제안 ${result.proposals.length}건 생성 · 확인 후 확정하세요`);
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
    setBatchMessage(`${document.fileName} 배정 중...`);
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
    setBatchMessage("분류 확정 및 평가결과 생성 중...");
    const result = await api("/api/references/batch-confirm", {
      method: "POST",
      body: { assignments: payload },
    });
    setBatchProposals([]);
    setAssignments({});
    onDashboardUpdate(result.dashboard);
    setBatchMessage(`${result.assigned.length}건 확정 완료 · 관련 평가항목 종합평가 갱신 완료`);
  }

  return (
    <main className="detail-main reference-main">
      <section className="detail-shell">
        <button className="back-button" type="button" onClick={onBack}>← 대시보드</button>
        <section className="reference-hero">
          <div>
            <p>Reference Archive</p>
            <h1>참고문헌 목록</h1>
            <span>{data.project.title}</span>
          </div>
          <div className="reference-summary">
            <article>
              <span>업로드 문서</span>
              <strong>{documents.length}건</strong>
            </article>
            <article>
              <span>총 용량</span>
              <strong>{Math.round(totalSize / 1024).toLocaleString()} KB</strong>
            </article>
          </div>
        </section>

        <section className="reference-panel">
          <div className="reference-head">
            <h2>업로드 된 모든 문서</h2>
            <p>평가 기준별 증빙자료, 사업개요서 연동본, 수동 추가 자료를 한곳에서 확인합니다.</p>
          </div>

          <div className="batch-upload-box">
            <div>
              <h3>일괄 업로드</h3>
              <p>여러 문서를 한 번에 올리면 AI가 평가 기준과 자료 항목을 제안합니다. 사용자가 수정·확정해야 실제 적재와 종합평가가 진행됩니다.</p>
            </div>
            <label className="batch-upload-button">
              문서 일괄 선택
              <input
                type="file"
                multiple
                onChange={(event) => {
                  uploadBatch(event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
          </div>
          {batchMessage && <p className="batch-message">{batchMessage}</p>}

          {pendingDocuments.length > 0 && (
            <section className="proposal-box">
              <div className="proposal-head">
                <div>
                  <h3>분류 제안 확인</h3>
                  <p>AI 제안을 검토한 뒤 평가 기준과 자료 항목을 최종 확정하세요. 확정 시 해당 평가항목의 LLM 종합평가가 실행됩니다.</p>
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
              <p>자동 매칭 포인트를 찾지 못한 문서는 평가 기준과 자료 항목을 직접 지정하거나 신규 항목명을 입력하세요.</p>
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

          {documents.length === 0 ? (
            <div className="empty-reference">
              <strong>아직 업로드 된 문서가 없습니다.</strong>
              <p>각 평가 기준 상세 화면에서 자료를 업로드하면 이 목록에 자동으로 표시됩니다.</p>
            </div>
          ) : (
            <div className="reference-table-wrap">
              <table className="reference-table">
                <thead>
                  <tr>
                    <th>No.</th>
                    <th>평가 기준</th>
                    <th>자료 항목</th>
                    <th>파일명</th>
                    <th>업로드 일시</th>
                    <th>크기</th>
                    <th>텍스트 저장</th>
                    <th>원본</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((document) => (
                    <tr
                      id={`reference-${document.referenceKey}`}
                      className={highlightKey === document.referenceKey ? "highlight-reference" : ""}
                      key={document.referenceKey}
                    >
                      <td className="reference-number">{document.referenceNumber}</td>
                      <td><span className="criterion-badge">{document.criterionName}</span></td>
                      <td>{document.evidenceName || "-"}</td>
                      <td>
                        <strong>{document.fileName}</strong>
                        {document.source === "project_overview" && <small>사업개요서 연동본</small>}
                      </td>
                      <td>{document.uploadedAt || "-"}</td>
                      <td>{Math.round((document.size || 0) / 1024).toLocaleString()} KB</td>
                      <td>
                        <span className={document.textPath ? "text-status ready" : "text-status pending"}>
                          {document.textPath ? "저장 완료" : "대기"}
                        </span>
                      </td>
                      <td>
                        <a className="download-link" href={document.downloadUrl} download>
                          다운로드
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function OverviewPreview({ preview, onClose, onProjectUpdate }) {
  const [currentPreview, setCurrentPreview] = useState(preview);
  const [uploadMessage, setUploadMessage] = useState("");
  const previewData = currentPreview;
  const sizeKb = Math.round(previewData.file.size / 1024).toLocaleString();

  async function uploadOverview(file) {
    setUploadMessage("사업개요서 수정본 업로드 중...");
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
    onProjectUpdate(result.project, result.dashboard);
    setUploadMessage(result.message);
  }

  return (
    <div className="preview-backdrop" role="dialog" aria-modal="true" aria-label="사업개요서 미리보기">
      <section className="preview-panel">
        <div className="preview-head">
          <div>
            <p>사업개요서 원본 미리보기</p>
            <h2>{previewData.project.title}</h2>
            <span>{previewData.project.period} / {previewData.project.budget}</span>
          </div>
          <button type="button" onClick={onClose} aria-label="미리보기 닫기">닫기</button>
        </div>

        <div className="preview-file">
          <strong>{previewData.file.name}</strong>
          <dl>
            <div><dt>파일 크기</dt><dd>{sizeKb} KB</dd></div>
            <div><dt>수정일</dt><dd>{previewData.file.lastModified || "-"}</dd></div>
            <div><dt>구분</dt><dd>{previewData.file.source === "uploaded" ? "수정 업로드본" : "원본 파일"}</dd></div>
            <div><dt>파일 경로</dt><dd>{previewData.file.path}</dd></div>
          </dl>
        </div>

        <div className="preview-sections">
          {previewData.sections.map((section) => (
            <article key={section.title}>
              <h3>{section.title}</h3>
              <p>{section.body}</p>
            </article>
          ))}
        </div>

        <div className="preview-actions">
          <a href={previewData.file.downloadUrl} target="_blank" rel="noreferrer">현재 사업개요서 열기</a>
          <label className="overview-upload-button">
            사업개요서 수정 업로드
            <input
              type="file"
              accept=".hwp,.hwpx,.pdf,.doc,.docx"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadOverview(file);
              }}
            />
          </label>
        </div>
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
    setMessage(`${name} 업로드 및 텍스트 저장 중...`);
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
    if (result.evaluationResult) setEvaluationResult(result.evaluationResult);
    if (result.dashboard) onDashboardUpdate(result.dashboard);
    setUploadingName("");
    setMessage(`${file.name} 업로드 완료 · 텍스트 저장 및 평가 요청 처리됨`);
  }

  async function deleteEvidence(name, documentId, fileName) {
    setMessage(`${fileName} 삭제 중...`);
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
    setMessage(`${result.audit.action} · ${result.audit.checkedAt}`);
  }

  return (
    <main className="detail-shell">
      <section className="detail-panel">
        <button className="back-button" type="button" onClick={onBack}>← 대시보드</button>
        <p className="signal detail-signal"><span></span>DAC 6 Criteria Detail</p>
        <div className="detail-title">
          <div>
            <h1>{criterion.name}</h1>
            <p>{criterion.definition}</p>
          </div>
          <div className="detail-score">
            <strong>{evaluationResult?.score || criterion.currentScore4 || "-"}</strong>
            <span>1~4점 평가</span>
          </div>
        </div>

        <section className="definition-box evaluation-result-box">
          <div className="evaluation-result-head">
            <div>
              <MarkdownBlock
                text={evaluationResult?.summary || "업로드된 자료를 기반으로 평가 결과가 표시됩니다."}
                criterionId={criterion.id}
                references={references}
                onCitationClick={onOpenReference}
              />
              <h2>평가결과</h2>
              <p>{evaluationResult?.summary || "업로드된 자료를 기반으로 적절성 평가 결과가 표시됩니다."}</p>
            </div>
            <span>{evaluationResult?.score ? `${evaluationResult.score}점` : "대기"}</span>
          </div>
          {evaluationResult?.sections?.length > 0 && (
            <div className="evaluation-sections">
              {evaluationResult.sections.map((section) => (
                <article key={section.title}>
                  <h3>{section.title}</h3>
                  <MarkdownBlock
                    text={section.body}
                    criterionId={criterion.id}
                    references={references}
                    onCitationClick={onOpenReference}
                  />
                  <p>{section.body}</p>
                </article>
              ))}
            </div>
          )}
          <small>Model: {evaluationResult?.model || "google/gemini-3.1-flash-lite"}</small>
        </section>

        {criterion.commonScoringNotes && criterion.scoringRubric && (
          <section className="scoring-box">
            <div className="scoring-head">
              <h2 className="dynamic-scoring-title">{criterion.name} 평가 기준</h2>
              <p className="dynamic-scoring-description">평가결과는 아래 공통 참고사항과 {criterion.name} 세부 질문별 1~4점 기준을 함께 적용합니다.</p>
              <p>평가결과는 아래 공통 참고사항과 적절성 핵심 질문별 1~4점 기준을 함께 적용합니다.</p>
            </div>
            <div className="common-score-grid">
              {criterion.commonScoringNotes.map((note) => (
                <article key={note.score}>
                  <strong>{note.score}점</strong>
                  <p>{note.criteria}</p>
                </article>
              ))}
            </div>
            <div className="question-rubrics">
              {criterion.scoringRubric.map((rubric) => (
                <section key={rubric.question} className="rubric-card">
                  <h3>{rubric.question}</h3>
                  <div className="rubric-levels">
                    {rubric.levels.map((level) => (
                      <div key={level.score}>
                        <span>{level.score}점</span>
                        <p>{level.criteria}</p>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </section>
        )}

        <section className="checklist-box">
          <div className="checklist-head">
            <div>
              <h2>업로드 해야 할 파일 목록</h2>
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

function App() {
  const [data, setData] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [view, setView] = useState("dashboard");
  const [highlightReferenceKey, setHighlightReferenceKey] = useState(null);
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
    setView("references");
  }

  useEffect(() => {
    api("/api/dashboard").then(setData);
  }, []);

  if (!data) {
    return (
      <main className="loading-screen">
        <strong>ODA M&E Dashboard</strong>
        <span>Python 백엔드에서 DAC 데이터를 불러오는 중입니다.</span>
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
            setView("dashboard");
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
      ) : (
        <Dashboard
          data={data}
          onSelect={(id) => {
            setSelectedId(id);
            setHighlightReferenceKey(null);
            setView("detail");
          }}
          onOpenReferences={() => openReference(null)}
          onProjectUpdate={(project, dashboard) => setData((current) => dashboard || { ...current, project })}
        />
      )}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
