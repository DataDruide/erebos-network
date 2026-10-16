.PHONY: help lock install verify build clean

help:
	@echo "Erebos Network — Build-Targets"
	@echo "  make lock      — requirements.lock neu generieren"
	@echo "  make install   — venv mit gelockten Versionen installieren"
	@echo "  make build     — Wheel bauen (dist/)"
	@echo "  make verify    — Reproduzierbarkeit prüfen (zweimal bauen)"
	@echo "  make clean     — build/ und dist/ löschen"

lock:
	python3 -m pip freeze --all | grep -vE '^(erebos-network|pip|setuptools|wheel|distribute)==' | sort -f > requirements.lock
	@echo "requirements.lock: $$(wc -l < requirements.lock) Pakete"

install:
	python3 -m pip install --require-virtualenv -r requirements.lock
	python3 -m pip install --require-virtualenv -e '.[dev,tools]'

build: clean
	python3 -m build --wheel --outdir dist
	@echo "dist/: $$(ls dist/)"

verify:
	bash scripts/verify_build.sh

clean:
	rm -rf build dist *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
