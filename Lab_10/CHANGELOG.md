# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-29

### Added
- Production packaging via `pyproject.toml`, building both wheel and sdist distributions.
- Configuration layer with Pydantic Settings supporting environment variables (`ENVIRONMENT`, `DATABASE_URL`, `LOG_LEVEL`).
- Multi-stage Docker containerization with non-root security user (`appuser`) and persistent volume support.
- Production REST API endpoints with FastAPI and health monitoring (`GET /health`).
- SQLite persistence layer with SQLAlchemy ORM and Alembic schema migrations.
- Comprehensive automated CI pipeline with GitHub Actions verifying linting, formatting, type checking, tests, packaging, and Docker build.
- In-memory and persistent repository interfaces with unit test coverage.
- Performance analytics and benchmark suite with Welford variance and multiprocessing acceleration.
