"""Quota removal must preserve accounting, concurrency and cancellation boundaries."""
from unittest.mock import MagicMock, patch
import pytest
from kodame_intake.ai import global_budget, job_budget


def reserve_with_stats(stats):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = stats
    with patch('kodame_intake.db.connection') as connection:
        connection.return_value.__enter__.return_value = conn
        result = global_budget.reserve('test-key-hash', 'task', 'model', 100, 1)
    return result, conn


OVER_LIMIT = dict(requests=10000,tokens=100_000_000,cost=1000,active=0,
                  account_cost=1000,job_requests=10000,job_cost=1000)


def test_disabled_usage_caps_still_record_reservations(monkeypatch):
    monkeypatch.setenv('AI_USAGE_LIMITS_ENABLED', 'false')
    result, conn = reserve_with_stats(OVER_LIMIT)
    assert result is not None
    assert any('INSERT INTO ai_request_reservations' in call.args[0] for call in conn.execute.call_args_list)


def test_disabled_usage_caps_do_not_remove_global_concurrency(monkeypatch):
    monkeypatch.setenv('AI_USAGE_LIMITS_ENABLED', 'false')
    monkeypatch.setenv('AI_GLOBAL_IN_FLIGHT', '4')
    result, conn = reserve_with_stats({**OVER_LIMIT,'active':4})
    assert result is None
    assert not any('INSERT INTO ai_request_reservations' in call.args[0] for call in conn.execute.call_args_list)


def test_limits_can_be_explicitly_reenabled(monkeypatch):
    monkeypatch.setenv('AI_USAGE_LIMITS_ENABLED', 'true')
    with pytest.raises(job_budget.BudgetExceeded):
        reserve_with_stats(OVER_LIMIT)


def test_zero_job_seconds_disables_total_runtime_cap(monkeypatch):
    monkeypatch.setenv('AI_JOB_SECONDS','0')
    with job_budget.job_budget('unlimited-job'):
        with patch.object(job_budget.time,'monotonic',return_value=float('inf')):
            assert job_budget.current_job() == 'unlimited-job'


def test_positive_runtime_cap_remains_supported(monkeypatch):
    monkeypatch.setenv('AI_JOB_SECONDS','1')
    with patch.object(job_budget.time,'monotonic',return_value=1):
        with job_budget.job_budget('bounded-job'):
            with patch.object(job_budget.time,'monotonic',return_value=3):
                with pytest.raises(job_budget.BudgetExceeded):
                    job_budget.current_job()
