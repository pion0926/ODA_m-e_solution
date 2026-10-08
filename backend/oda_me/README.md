# ODA M&E Backend Structure

`backend/app.py` is now only the process entry point. The application logic lives in this package, grouped by the workflow a maintainer sees in the product.

```text
backend/
  app.py                         # thin server entry point
  evaluation_specs.py            # DAC criteria and evidence specification
  report_prompts.py              # 27 report-part prompt definitions
  oda_me/
    core.py                      # paths, constants, project/sample metadata
    runtime.py                   # module bootstrap and public app namespace
    clients/
      openrouter.py              # OpenRouter chat client
    utils/
      common.py                  # small shared helpers
    project/
      inference.py               # project title, period, budget inference
    documents/
      text_extraction.py         # HWP/HWPX/PDF/XLSX/PPTX text extraction
      evidence_store.py          # upload metadata, evidence assignment, matching
      reference_corpus.py        # section/criterion reference corpus builders
    evaluations/
      engine.py                  # criterion scoring prompts and LLM evaluation
    reports/
      context.py                 # report context, sample references, contracts
      export_builders.py         # DOCX/XLSX/PPTX/HWP/HWPX package builders
      editor.py                  # 27-part editor, auto-draft, AI revision
    hwpx/
      formatting.py              # report prose cleanup and formatting helpers
      patchers.py                # HWPX XML manifest/table/body patching
    api/
      dashboard.py               # dashboard payload and readiness summary
      http_server.py             # HTTP route handler and server startup
```

## Main Flow

1. `api/http_server.py` receives requests.
2. `documents/evidence_store.py` saves and assigns uploaded evidence.
3. `evaluations/engine.py` generates criterion scores from assigned evidence.
4. `reports/editor.py` generates or revises the 27 report parts.
5. `hwpx/patchers.py` applies report-part values to the fixed HWPX template.
6. `reports/export_builders.py` packages downloads and report artifacts.

`runtime.py` keeps behavior compatible while the former monolith is split. New code should prefer explicit imports from the module that owns the behavior.
