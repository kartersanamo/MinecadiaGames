import functools
import sys
import time
from pathlib import Path

from core.loggers import log_tasks


def _ensure_errors_path() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def task(action_name: str, log: bool = None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                time_elapsed = round((time.perf_counter() - start_time), 2)
                if time_elapsed > 3:
                    log_tasks.warning(
                        f"{action_name} took a long time to complete and finished in {time_elapsed}s"
                    )
                elif log:
                    log_tasks.info(f"{action_name} completed in {time_elapsed}s")
                return result
            except Exception as error:
                _ensure_errors_path()
                from _errors.logging import log_exception

                log_exception(
                    log_tasks,
                    error,
                    bot_name="Games",
                    component=action_name,
                    extra={"elapsed_s": round((time.perf_counter() - start_time), 2)},
                )
                raise error

        return wrapper

    return decorator
