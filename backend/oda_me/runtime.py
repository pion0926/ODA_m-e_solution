from __future__ import annotations

from types import ModuleType

from . import core
from .clients import openrouter
from .utils import common
from .documents import text_extraction, reference_corpus, evidence_store
from .project import inference
from .evaluations import engine as evaluations_engine
from .reports import context as report_context, export_builders, editor as report_editor
from .hwpx import formatting, patchers
from .api import dashboard, http_server

# Legacy functions were split by responsibility, but many still reference shared
# symbols by their original global names. During the migration, publish every
# public symbol into each module namespace so behavior stays identical while the
# file tree is understandable and future edits can move toward explicit imports.
MODULES: list[ModuleType] = [
    core,
    openrouter,
    common,
    text_extraction,
    reference_corpus,
    inference,
    evidence_store,
    evaluations_engine,
    report_context,
    export_builders,
    report_editor,
    formatting,
    patchers,
    dashboard,
    http_server,
]


def _public_symbols(module: ModuleType) -> dict[str, object]:
    return {
        name: value
        for name, value in module.__dict__.items()
        if not name.startswith("_")
    }


namespace: dict[str, object] = {}
for module in MODULES:
    namespace.update(_public_symbols(module))

for module in MODULES:
    module.__dict__.update(namespace)

globals().update(namespace)

OdaHandler = http_server.OdaHandler
main = http_server.main
