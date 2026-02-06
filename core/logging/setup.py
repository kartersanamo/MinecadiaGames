import logging
import logging.config
import logging.handlers
from pathlib import Path
from datetime import datetime
import pytz
from typing import Optional


EST = pytz.timezone('US/Eastern')
GRAY = "\033[90m"
LIGHT_PINK = "\033[95m"
RESET = "\033[0m"


class ESTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, EST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f EST")


class CustomTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def __init__(self, filename, when='midnight', interval=1, backupCount=7, encoding=None, delay=False, utc=False, atTime=None):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        if not hasattr(self, 'suffix'):
            self.suffix = "%Y-%m-%d"
    
    def doRollover(self):
        self.stream.close()
        current_time = int(self.rolloverAt - self.interval)
        dt = datetime.fromtimestamp(current_time, EST)
        dfn = dt.strftime(self.suffix)
        self.filename = dfn
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                import os
                os.remove(s)
        self.mode = 'w'
        self.stream = self._open()
        self.rolloverAt = self.rolloverAt + self.interval


def setup_logging(log_dir: str = None):
    if log_dir is None:
        from pathlib import Path
        log_dir = str(Path(__file__).parent.parent.parent / "logs")
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    current_time_est = datetime.now(EST)
    log_filename = log_path / f"{current_time_est.strftime('%Y-%m-%d')}.log"
    
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "root": {
            "level": "INFO",
            "handlers": ["console", "file"]
        },
        "formatters": {
            "file": {
                "format": "%(levelname)-10s  %(asctime)s  %(funcName)-15s : %(message)s",
                "()": ESTFormatter
            },
            "standard": {
                "format": f"{GRAY}%(asctime)s{RESET} %(levelname)-8s {LIGHT_PINK}%(name)s{RESET} %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "()": ESTFormatter
            }
        },
        "handlers": {
            "console": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "standard"
            },
            "file": {
                "level": "DEBUG",
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(log_filename),
                "when": "midnight",
                "interval": 1,
                "backupCount": 7,
                "formatter": "file"
            }
        },
        "loggers": {
            "Tasks": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            "Commands": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            "ChatGames": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            "DMGames": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            "discord": {
                "handlers": ["file"],
                "level": "INFO",
                "propagate": False
            },
            "asyncio": {
                "handlers": ["file"],
                "level": "ERROR",
                "propagate": False
            }
        }
    }
    
    logging.config.dictConfig(LOGGING_CONFIG)
    
    for logger_name in LOGGING_CONFIG["loggers"]:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.handlers.TimedRotatingFileHandler):
                logger.removeHandler(handler)
                new_handler = CustomTimedRotatingFileHandler(
                    handler.baseFilename,
                    when=handler.when,
                    interval=handler.interval,
                    backupCount=handler.backupCount,
                    encoding=handler.encoding,
                    delay=handler.delay,
                    utc=handler.utc,
                    atTime=handler.atTime
                )
                new_handler.setFormatter(handler.formatter)
                logger.addHandler(new_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

