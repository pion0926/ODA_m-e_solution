from __future__ import annotations

import argparse
import uuid

from .db import connection, open_pool, tenant_context
from .project_overview import generate_local_bootstrap_overview


def main() -> None:
    parser = argparse.ArgumentParser(description="사업계획서·PDM의 기존 로컬 분석으로 사업개요를 갱신합니다.")
    parser.add_argument("project_id", type=uuid.UUID)
    args = parser.parse_args()
    open_pool()
    with tenant_context(args.project_id):
        with connection() as conn, conn.transaction():
            conn.execute("DELETE FROM project_overviews")
        overview_id = generate_local_bootstrap_overview()
        with connection() as conn, conn.transaction():
            row = conn.execute("SELECT overview FROM project_overviews WHERE id=%s", (overview_id,)).fetchone()
            project_name = row["overview"]["project_name"]["text"].strip()
            conn.execute("UPDATE projects SET name=%s,updated_at=now() WHERE id=%s", (project_name, args.project_id))
    print(f"사업계획서·PDM 기반 사업개요 생성 완료: {overview_id}")


if __name__ == "__main__":
    main()
