# Convenience targets. Everything here is a one-liner you could type yourself.

.PHONY: hooks install gates docs certify

hooks:            ## enable the client-side pre-push protection
	git config core.hooksPath .githooks
	@chmod +x .githooks/* 2>/dev/null || true
	@echo "pre-push hook enabled. See .githooks/pre-push for what it refuses."

install:          ## venv + editable install with analysis extras
	python3 -m venv .venv
	./.venv/bin/pip install -q --upgrade pip
	./.venv/bin/pip install -q -e '.[analysis]'
	@echo "installed. `forge` is at ./.venv/bin/forge"

gates:            ## everything CI runs
	./.venv/bin/forge reconcile --strict
	./.venv/bin/forge prompt lint

docs:             ## regenerate every generated artefact
	./.venv/bin/forge docs framework
	./.venv/bin/forge docs agents
	./.venv/bin/forge bundle fresh
	@test -s label/label.yaml && ./.venv/bin/forge docs catalog || true

certify:          ## the fork approval gate
	./.venv/bin/forge certify
