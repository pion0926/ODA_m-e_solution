from __future__ import annotations
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ..db import connection, open_pool, pool, tenant_context
from ..report_sections import sync_report_sections
from ..settings import ORIGINALS_DIR


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv('RUN_MIGRATIONS_ON_START', 'true').lower() == 'true':
        open_pool()
    else:
        pool.open(wait=True)
    with tenant_context(system=True):
        with connection() as conn, conn.transaction():
            projects = conn.execute("SELECT id FROM projects WHERE status='active'").fetchall()
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    for project in projects:
        with tenant_context(project["id"]):
            sync_report_sections()
    yield
    pool.close()
