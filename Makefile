.PHONY: dev test lint

FLASK_APP ?= web_control:app

DEV_PORT ?= 5050

DEV_ENV = FLASK_APP=$(FLASK_APP) FLASK_ENV=development

dev:
	$(DEV_ENV) flask run -p $(DEV_PORT)

test:
	pytest -q

lint:
	@if command -v ruff >/dev/null 2>&1; then \
	ruff check; \
	else \
	echo "ruff not installed; skipping"; \
fi
