UV ?= uv

.PHONY: install run lint format build

install:
	$(UV) sync --locked

run:
	$(UV) run --locked valutatrade

lint:
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .

format:
	$(UV) run --locked ruff check --fix .
	$(UV) run --locked ruff format .

build:
	$(UV) build
