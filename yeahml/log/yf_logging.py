import logging
from pathlib import Path
from typing import Any


def _get_level(level_str: str) -> Any:
    level = None
    if level_str == "DEBUG":
        level = logging.DEBUG
    elif level_str == "INFO":
        level = logging.INFO
    elif level_str == "WARNING":
        level = logging.WARNING
    elif level_str == "ERROR":
        level = logging.ERROR
    elif level_str == "CRITICAL":
        level = logging.CRITICAL
    else:
        level = None

    return level


# I'm not convinced this is the best way to accomplish creating loggers
def config_logger(full_exp_path: str, log_cdict: dict, log_type: str) -> Any:

    # formatting
    c_fmt = logging.Formatter(log_cdict["console"]["format_str"])
    f_fmt = logging.Formatter(log_cdict["file"]["format_str"])

    ACCEPTED_LOGGERS = ["build", "train", "eval", "graph", "preds", "config"]
    if log_type not in ACCEPTED_LOGGERS:
        raise ValueError(
            f"The requested logger type is not currently supported: {log_type}"
        )

    cur_logger = logging.getLogger(f"{log_type}_logger")
    cur_logger.propagate = False
    cur_logger.setLevel(_get_level("DEBUG"))  # set base to lowest level
    stream_handler = logging.StreamHandler()

    # set file path
    log_base_path = Path(full_exp_path).joinpath("yeahml_logs")
    log_base_path.mkdir(parents=True, exist_ok=True)
    log_full_path = log_base_path.joinpath(f"{log_type}.log")

    file_handler = logging.FileHandler(str(log_full_path))
    stream_handler.setLevel(_get_level(log_cdict["console"]["level"].upper()))
    file_handler.setLevel(_get_level(log_cdict["file"]["level"].upper()))
    stream_handler.setFormatter(c_fmt)
    file_handler.setFormatter(f_fmt)
    if not len(cur_logger.handlers):
        # if the logger is called n times, only add handlers once
        cur_logger.addHandler(stream_handler)
        cur_logger.addHandler(file_handler)
    return cur_logger
