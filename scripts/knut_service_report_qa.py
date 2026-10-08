"""Repeatable service checks; credentials only from environment, no DB writes."""
import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1] / "output/knut-e2e-20260911"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("performance", "export", "status", "download"))
    parser.add_argument("export_id", nargs="?")
    args = parser.parse_args()
    with httpx.Client(base_url=os.getenv("KNUT_QA_BASE", "http://127.0.0.1:8002/api/v2"), timeout=180) as client:
        response = client.post("/auth/login", json={"email": "knut", "password": os.environ["KNUT_QA_PASSWORD"]})
        response.raise_for_status()
        assert response.json()["project"]["id"] == "ee8b8006-96eb-4f69-9778-233c42f6f009"
        if args.action == "performance":
            report = {}
            for endpoint in ("/project/lifecycle", "/report/sections/criteria-other", "/dashboard"):
                durations = []
                for _ in range(20):
                    start = time.monotonic()
                    response = client.get(endpoint)
                    response.raise_for_status()
                    durations.append(round((time.monotonic()-start)*1000, 2))
                report[endpoint] = {"requests":20, "p50_ms": statistics.median(durations),
                                    "p95_ms": sorted(durations)[18], "max_ms": max(durations)}
            (ROOT / "service-api-performance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report))
        elif args.action == "export":
            response = client.post("/report/exports", json={})
            result = {"status_code": response.status_code, "body": response.json()}
            (ROOT / "service-export-start.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False))
        else:
            endpoint = f"/report/exports/{args.export_id}" if args.export_id else "/report/exports/latest"
            response = client.get(endpoint)
            response.raise_for_status()
            result = response.json()
            (ROOT / "service-export-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({key: result.get(key) for key in ("id", "status", "progress", "stage", "message", "error_message", "file_name")}, ensure_ascii=False))
            if args.action == "download":
                assert result["status"] == "completed", result["status"]
                response = client.get(result["download_url"].removeprefix("/api/v2"))
                response.raise_for_status()
                path = ROOT / "KNUT-service-final-report.hwpx"
                path.write_bytes(response.content)
                print(json.dumps({"path":str(path),"bytes":len(response.content),"sha256":hashlib.sha256(response.content).hexdigest()}))


if __name__ == "__main__":
    main()
