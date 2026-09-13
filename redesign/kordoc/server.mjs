import http from "node:http";
import {
  hwpxToProfile,
  openHwpxDocument,
  parse,
  renderHwpxToSvg,
  validateHwpx,
} from "kordoc";

const MAX_BYTES = 64 * 1024 * 1024;

function send(res, status, body) {
  const data = Buffer.from(JSON.stringify(body));
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Content-Length": data.length });
  res.end(data);
}

function sendSvg(res, status, body) {
  const data = Buffer.from(body);
  res.writeHead(status, { "Content-Type": "image/svg+xml; charset=utf-8", "Content-Length": data.length });
  res.end(data);
}

function decodeXmlText(value) {
  return String(value || "")
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&#(\d+);/g, (_match, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_match, code) => String.fromCodePoint(parseInt(code, 16)));
}

function renderedPageTexts(svg) {
  return String(svg || "")
    .split(/(?=<g\s+data-page="\d+")/g)
    .slice(1)
    .map((fragment) => {
      const page = Number(fragment.match(/<g\s+data-page="(\d+)"/)?.[1] || 0);
      const text = [...fragment.matchAll(/<text\b[^>]*>([\s\S]*?)<\/text>/g)]
        .map((match) => decodeXmlText(match[1]).replace(/\s+/g, " ").trim())
        .filter(Boolean)
        .join("\n");
      return { page_number: page, text };
    })
    .filter((item) => item.page_number > 0);
}

function numericAttribute(attributes, name) {
  const match = String(attributes || "").match(new RegExp(`\\b${name}="([\\d.\\-]+)"`));
  return match ? Number(match[1]) : Number.NaN;
}

function renderedTextLineOverlapRisks(svg) {
  const risks = [];
  const pageFragments = String(svg || "")
    .split(/(?=<g\s+data-page="\d+")/g)
    .slice(1);
  for (const fragment of pageFragments) {
    const pageNumber = Number(fragment.match(/<g\s+data-page="(\d+)"/)?.[1] || 0);
    const items = [...fragment.matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)]
      .map((match) => {
        const attributes = match[1];
        const text = decodeXmlText(match[2]).replace(/\s+/g, " ").trim();
        const x = numericAttribute(attributes, "x");
        const y = numericAttribute(attributes, "y");
        const fontSize = numericAttribute(attributes, "font-size");
        const declaredLength = numericAttribute(attributes, "textLength");
        const width = Number.isFinite(declaredLength)
          ? declaredLength
          : Math.max(fontSize, text.length * fontSize * 0.55);
        const anchor = attributes.match(/\btext-anchor="([^"]+)"/)?.[1] || "start";
        const left = anchor === "middle" ? x - width / 2 : anchor === "end" ? x - width : x;
        return { text, y, fontSize, left, right: left + width };
      })
      .filter((item) => (
        item.text
        && Number.isFinite(item.y)
        && Number.isFinite(item.fontSize)
        && Number.isFinite(item.left)
        && Number.isFinite(item.right)
      ))
      .sort((a, b) => a.y - b.y || a.left - b.left);

    const lines = [];
    for (const item of items) {
      const current = lines.at(-1);
      if (current && Math.abs(current.y - item.y) <= 0.35) {
        current.items.push(item);
        current.y = current.items.reduce((total, row) => total + row.y, 0) / current.items.length;
        current.fontSize = Math.max(current.fontSize, item.fontSize);
      } else {
        lines.push({ y: item.y, fontSize: item.fontSize, items: [item] });
      }
    }

    for (let index = 1; index < lines.length; index += 1) {
      const above = lines[index - 1];
      const below = lines[index];
      const baselineGap = below.y - above.y;
      const fontSize = Math.max(above.fontSize, below.fontSize);
      if (baselineGap <= 0.35 || baselineGap >= fontSize * 0.85) continue;
      let collision = null;
      for (const upperItem of above.items) {
        for (const lowerItem of below.items) {
          const overlapWidth = Math.min(upperItem.right, lowerItem.right)
            - Math.max(upperItem.left, lowerItem.left);
          const shorterWidth = Math.min(
            upperItem.right - upperItem.left,
            lowerItem.right - lowerItem.left,
          );
          if (overlapWidth >= 4 && overlapWidth >= shorterWidth * 0.2) {
            collision = { upperItem, lowerItem, overlapWidth };
            break;
          }
        }
        if (collision) break;
      }
      if (!collision) continue;
      risks.push({
        page_number: pageNumber,
        upper_y: Number(above.y.toFixed(2)),
        lower_y: Number(below.y.toFixed(2)),
        baseline_gap: Number(baselineGap.toFixed(2)),
        font_size: Number(fontSize.toFixed(2)),
        overlap_width: Number(collision.overlapWidth.toFixed(2)),
        upper_text: collision.upperItem.text.slice(0, 120),
        lower_text: collision.lowerItem.text.slice(0, 120),
      });
      if (risks.length >= 50) return risks;
    }
  }
  return risks;
}

async function readBody(req, res) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BYTES) {
      send(res, 413, { ok: false, error: "file too large" });
      return null;
    }
    chunks.push(chunk);
  }
  return new Uint8Array(Buffer.concat(chunks));
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/healthz") return send(res, 200, { ok: true, service: "kodame-kordoc" });
  if (req.method !== "POST" || !["/validate", "/analyze", "/render"].includes(req.url)) {
    return send(res, 404, { ok: false, error: "not found" });
  }
  const bytes = await readBody(req, res);
  if (!bytes) return;
  try {
    const validation = await validateHwpx(bytes);
    const parsed = await parse(bytes);
    if (!parsed?.success) return send(res, 422, { ok: false, error: parsed?.error?.message || "kordoc parse failed", validation });
    if (req.url === "/render") {
      const rendered = await renderHwpxToSvg(bytes, { reflow: true, reflowMode: "keep" });
      return sendSvg(res, 200, rendered.svg);
    }
    if (req.url === "/analyze") {
      const [profile, session, rendered] = await Promise.all([
        hwpxToProfile(Buffer.from(bytes)),
        openHwpxDocument(bytes),
        renderHwpxToSvg(bytes, { reflow: true, reflowMode: "keep" }),
      ]);
      const capabilityCounts = session.capabilities().reduce((counts, item) => {
        counts[item.capability] = (counts[item.capability] || 0) + 1;
        return counts;
      }, {});
      const tables = (profile.tables || []).map((table) => ({
        table_index: table.table_index,
        rows: table.rows,
        cols: table.cols,
        anchor_text: table.anchor_text || "",
        width_hwpunit: table.width_hwpunit || "",
        col_widths_hwpunit: table.col_widths_hwpunit || [],
      }));
      const lineOverlapRisks = renderedTextLineOverlapRisks(rendered.svg);
      return send(res, 200, {
        ok: true,
        validation,
        parser: "kordoc",
        block_count: Array.isArray(parsed.blocks) ? parsed.blocks.length : 0,
        markdown_chars: typeof parsed.markdown === "string" ? parsed.markdown.length : 0,
        session: { block_count: session.blocks.length, capability_counts: capabilityCounts },
        profile: { schema_version: profile.schema_version || "", table_count: tables.length, tables },
        render: {
          page_count: rendered.pageCount,
          width_pt: rendered.width,
          height_pt: rendered.height,
          warnings: rendered.warnings,
          stats: {
            ...rendered.stats,
            line_overlap_risk_count: lineOverlapRisks.length,
          },
          page_texts: renderedPageTexts(rendered.svg),
          line_overlap_risks: lineOverlapRisks,
        },
      });
    }
    return send(res, 200, {
      ok: true,
      validation,
      parser: "kordoc",
      block_count: Array.isArray(parsed.blocks) ? parsed.blocks.length : 0,
      markdown_chars: typeof parsed.markdown === "string" ? parsed.markdown.length : 0
    });
  } catch (error) {
    return send(res, 422, { ok: false, error: String(error?.message || error) });
  }
});

server.listen(8200, "0.0.0.0");
