"""модуль завантаження та валідації конфігурації"""

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

from student_manager.exceptions import ConfigurationError

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True, slots=True)
class ProcessingConfig:
    minimum_grade: float
    skip_invalid: bool


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str
    path: Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    input_path: Path
    output_path: Path
    processing: ProcessingConfig
    logging: LoggingConfig


def _resolve_relative_path(base_dir: Path, raw_path: Any, field_name: str) -> Path:
    if not isinstance(raw_path, (str, Path)) or isinstance(raw_path, bool):
        raise ConfigurationError(f"Field '{field_name}' must be a valid path string")
    path_str = str(raw_path).strip()
    if not path_str:
        raise ConfigurationError(f"Field '{field_name}' path cannot be empty")
    p = Path(path_str)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    else:
        p = p.resolve()
    return p


def validate_config(config: AppConfig) -> None:
    # перевіряємо поріг оцінки
    min_grade = config.processing.minimum_grade
    if not isinstance(min_grade, (int, float)) or isinstance(min_grade, bool):
        raise ConfigurationError("processing.minimum_grade must be a number")
    if not math.isfinite(min_grade) or not 0 <= min_grade <= 100:
        raise ConfigurationError(
            "processing.minimum_grade must be a finite number between 0 and 100"
        )

    # перевіряємо булевий прапорець
    if type(config.processing.skip_invalid) is not bool:
        raise ConfigurationError(
            "processing.skip_invalid must be a boolean (true or false)"
        )

    # перевіряємо рівень логування
    lvl = config.logging.level.upper()
    if lvl not in VALID_LOG_LEVELS:
        raise ConfigurationError(
            f"logging.level '{config.logging.level}' is invalid; must be one of {sorted(VALID_LOG_LEVELS)}"
        )

    # перевіряємо існування вхідного файлу
    if not config.input_path.exists():
        raise ConfigurationError(f"Input file does not exist: {config.input_path}")
    if not config.input_path.is_file():
        raise ConfigurationError(
            f"Input path must be a regular file: {config.input_path}"
        )

    # забороняємо збіг шляхів шоб не затерти вхідні дані чи логи
    in_res = config.input_path.resolve()
    out_res = config.output_path.resolve()
    log_res = config.logging.path.resolve()

    if in_res == out_res:
        raise ConfigurationError(f"Input path and output path collide: {in_res}")
    if in_res == log_res:
        raise ConfigurationError(f"Input path and log path collide: {in_res}")
    if out_res == log_res:
        raise ConfigurationError(f"Output path and log path collide: {out_res}")


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_data = yaml.safe_load(file)
    except FileNotFoundError as err:
        raise ConfigurationError(
            f"Configuration file not found: {config_path}"
        ) from err
    except (OSError, UnicodeDecodeError) as err:
        raise ConfigurationError(
            f"Cannot read configuration file {config_path}: {err}"
        ) from err
    except yaml.YAMLError as err:
        raise ConfigurationError(
            f"Invalid YAML configuration syntax in {config_path}: {err}"
        ) from err

    if not isinstance(raw_data, dict):
        raise ConfigurationError(
            f"Configuration file root must be a YAML mapping (dict), got {type(raw_data).__name__}"
        )

    # перевіряємо обов'язкові секції
    required_sections = ("input", "output", "processing", "logging")
    for section in required_sections:
        if section not in raw_data or not isinstance(raw_data[section], dict):
            raise ConfigurationError(
                f"Configuration is missing required section '{section}' or it is not a mapping"
            )

    base_dir = config_path.resolve().parent

    # валідація секції input
    if "path" not in raw_data["input"]:
        raise ConfigurationError("Missing 'path' in 'input' section")
    input_path = _resolve_relative_path(
        base_dir, raw_data["input"]["path"], "input.path"
    )

    # валідація секції output
    if "path" not in raw_data["output"]:
        raise ConfigurationError("Missing 'path' in 'output' section")
    output_path = _resolve_relative_path(
        base_dir, raw_data["output"]["path"], "output.path"
    )

    # валідація секції processing
    proc_dict = raw_data["processing"]
    if "minimum_grade" not in proc_dict:
        raise ConfigurationError("Missing 'minimum_grade' in 'processing' section")
    if "skip_invalid" not in proc_dict:
        raise ConfigurationError("Missing 'skip_invalid' in 'processing' section")

    raw_min_grade = proc_dict["minimum_grade"]
    if type(raw_min_grade) not in (int, float) or isinstance(raw_min_grade, bool):
        raise ConfigurationError(
            "processing.minimum_grade must be a number (float or int), not boolean or string"
        )
    min_grade = float(raw_min_grade)

    raw_skip = proc_dict["skip_invalid"]
    if type(raw_skip) is not bool:
        raise ConfigurationError(
            "processing.skip_invalid must be a boolean (true or false), not string or int"
        )

    # валідація секції logging
    log_dict = raw_data["logging"]
    if "level" not in log_dict:
        raise ConfigurationError("Missing 'level' in 'logging' section")
    if "path" not in log_dict:
        raise ConfigurationError("Missing 'path' in 'logging' section")

    raw_level = log_dict["level"]
    if not isinstance(raw_level, str) or isinstance(raw_level, bool):
        raise ConfigurationError("logging.level must be a string")
    log_level = raw_level.strip().upper()
    if log_level not in VALID_LOG_LEVELS:
        raise ConfigurationError(
            f"logging.level '{raw_level}' is invalid; must be one of {sorted(VALID_LOG_LEVELS)}"
        )

    log_path = _resolve_relative_path(base_dir, log_dict["path"], "logging.path")

    config = AppConfig(
        input_path=input_path,
        output_path=output_path,
        processing=ProcessingConfig(
            minimum_grade=min_grade,
            skip_invalid=raw_skip,
        ),
        logging=LoggingConfig(
            level=log_level,
            path=log_path,
        ),
    )

    validate_config(config)
    return config


class Settings(BaseSettings):
    app_name: str = "Student Manager"
    environment: str = "development"
    app_env: str = "development"
    database_url: str = "sqlite:///app.db"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production" or self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
