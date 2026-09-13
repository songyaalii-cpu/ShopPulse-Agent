from arq import cron, run_worker
from arq.connections import RedisSettings

from shoppulse.observability.logging import configure_logging
from shoppulse.settings import get_settings
from shoppulse.worker.jobs import execute_analysis_job, execute_evaluation_job, recover_stale_runs

cfg = get_settings()


class WorkerSettings:
    functions = [execute_analysis_job, execute_evaluation_job]
    cron_jobs = [cron(recover_stale_runs, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55})]
    redis_settings = RedisSettings.from_dsn(cfg.redis_url)
    max_jobs = cfg.worker_concurrency
    job_timeout = cfg.run_timeout_seconds
    max_tries = cfg.run_max_retries + 1
    queue_name = f"{cfg.redis_key_prefix}queue"
    health_check_key = f"{cfg.redis_key_prefix}worker:health"


def main():
    configure_logging(cfg.log_level, "worker")
    run_worker(WorkerSettings)
