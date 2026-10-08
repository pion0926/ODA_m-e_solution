"""Replay KNUT conversion with cached visuals; never write report state or call AI."""
import json
import uuid
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager

from kodame_intake.db import open_pool, tenant_context
from kodame_intake import report_exporter as exporter

ROOT = Path("/workspace/output/knut-e2e-20260911/service-layout-diagnostic")
ROOT.mkdir(parents=True, exist_ok=True)
open_pool()
original_connection = exporter.connection
original_analyze = exporter.analyze_hwpx


@contextmanager
def readonly_connection():
    with original_connection() as connection:
        class Guard:
            def transaction(self):
                return connection.transaction()
            def execute(self, sql, values=None):
                if not sql.strip().upper().startswith("SELECT"):
                    print("REPORT_STATE_WRITE_SUPPRESSED", flush=True)
                    return None
                return connection.execute(sql, values)
        yield Guard()


def analyze(data, *args, **kwargs):
    ROOT.joinpath("candidate.hwpx").write_bytes(data)
    result = original_analyze(data, *args, **kwargs)
    ROOT.joinpath("analysis.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


with tenant_context("ee8b8006-96eb-4f69-9778-233c42f6f009"), \
     patch.object(exporter, "connection", readonly_connection), \
     patch.object(exporter, "_update", lambda *args: print(args[1:4], flush=True)), \
     patch.object(exporter, "EXPORT_DIR", ROOT), \
     patch.object(exporter, "analyze_hwpx", analyze), \
     patch.object(exporter, "build_theory_visual_artifacts", side_effect=RuntimeError("Replay refuses external model calls")), \
     patch.object(exporter, "save_theory_artifact", lambda *args: None):
    exporter._run_report_export(uuid.uuid4())
