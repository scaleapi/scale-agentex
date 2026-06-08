# Spark AuthZ E2E tests for scale-agentex.
#
# Target conventions
# ------------------
# Targets are grouped so you can run a single test file, all tests for a
# resource, all tests for a logical category, or the whole suite. Future
# resources slot into one of these groups by adding test files and
# updating the matching aggregate target — no new flat targets unless
# the resource is novel.
#
#   test                       all tests, every group
#   test-direct-resources      everything with its own SpiceDB type
#                              (agent, task, api_key, …)
#   test-sub-resources         everything that delegates to a parent
#                              (event, task_state, message, tracker, checkpoint)
#   test-<resource>            all cases for one resource
#                              (e.g. test-api-key, test-event)
#   test-<resource>-<case>     one case for one resource
#                              (e.g. test-api-key-create)
#
# When a parent grouping makes sense (e.g. "all task sub-resources"), add
# a test-<parent>-sub-resources target alongside the resource targets.

VENV ?= venv
PYTHON ?= python3
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

# Test-file globs. Update these (NOT individual case targets) when adding
# a new test file for an existing resource.
EVENT_TESTS := tests/test_event_authz.py

# Aggregate groupings — extend these as resources are added.
# Direct-resource targets land with their own PRs (e.g. api_key).
SUB_RESOURCE_TESTS := $(EVENT_TESTS)
# Future sub-resource additions go here:
#   SUB_RESOURCE_TESTS += $(STATE_TESTS) $(MESSAGE_TESTS) $(TRACKER_TESTS) $(CHECKPOINT_TESTS)

.PHONY: install test \
        test-sub-resources \
        test-event \
        clean help

help:
	@echo "scale-agentex Spark AuthZ E2E tests"
	@echo ""
	@echo "Setup:"
	@echo "  make install                 venv + deps (one-time)"
	@echo ""
	@echo "Run everything:"
	@echo "  make test                    all tests"
	@echo ""
	@echo "Run a logical group:"
	@echo "  make test-sub-resources      resources that delegate to a parent"
	@echo ""
	@echo "Run one resource:"
	@echo "  make test-event              all AGX1-331 cases"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) tests/ -v

# ---------------------------------------------------------------------------
# Logical groupings
# ---------------------------------------------------------------------------

test-sub-resources:
	$(PYTEST) $(SUB_RESOURCE_TESTS) -v

# ---------------------------------------------------------------------------
# Sub-resources (delegate authz to a parent)
# ---------------------------------------------------------------------------

# AGX1-331 — events delegate to parent agent
test-event:
	$(PYTEST) $(EVENT_TESTS) -v

clean:
	rm -rf $(VENV) .pytest_cache __pycache__
	find . -name __pycache__ -type d -exec rm -rf {} +
	find . -name '*.pyc' -delete
