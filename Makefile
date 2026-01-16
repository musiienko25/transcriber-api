.PHONY: help install dev test lint format run docker-build docker-up docker-down clean

help:
	@echo "Transcriber API - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install     Install dependencies"
	@echo "  make dev         Install dev dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run         Run the API server"
	@echo "  make test        Run tests"
	@echo "  make lint        Run linter"
	@echo "  make format      Format code"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  Build Docker images"
	@echo "  make docker-up     Start all services"
	@echo "  make docker-down   Stop all services"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean       Clean temp files"

install:
	pip install -r requirements.txt

dev:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

lint:
	ruff check app tests

format:
	ruff format app tests

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-prod-up:
	docker-compose -f docker-compose.prod.yml up -d

docker-prod-down:
	docker-compose -f docker-compose.prod.yml down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage .mypy_cache .ruff_cache
