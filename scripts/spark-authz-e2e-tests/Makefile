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
#                              (agent, task, api_key)
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
API_KEY_TESTS := tests/test_api_key_create.py tests/test_api_key_get.py tests/test_api_key_list.py tests/test_api_key_delete.py
STATE_TESTS := tests/test_state_list_get.py

# Aggregate groupings — extend these as resources are added.
DIRECT_RESOURCE_TESTS := $(API_KEY_TESTS)
# Future direct-resource additions go here:
#   DIRECT_RESOURCE_TESTS += $(AGENT_TESTS) $(TASK_TESTS)
SUB_RESOURCE_TESTS := $(STATE_TESTS)

.PHONY: install test \
        test-direct-resources \
        test-sub-resources \
        test-api-key test-api-key-create test-api-key-get test-api-key-list test-api-key-delete \
        test-state test-state-list-get \
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
	@echo "  make test-direct-resources   resources with their own SpiceDB type"
	@echo "  make test-sub-resources      resources that delegate to a parent"
	@echo ""
	@echo "Run one resource:"
	@echo "  make test-api-key            all AGX1-325 cases"
	@echo "  make test-state              all AGX1-327 state cases"
	@echo ""
	@echo "Run one case:"
	@echo "  make test-api-key-{create,get,list,delete}"
	@echo "  make test-state-list-get"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) tests/ -v

# ---------------------------------------------------------------------------
# Logical groupings
# ---------------------------------------------------------------------------

test-direct-resources:
	$(PYTEST) $(DIRECT_RESOURCE_TESTS) -v

test-sub-resources:
	$(PYTEST) $(SUB_RESOURCE_TESTS) -v

# ---------------------------------------------------------------------------
# Direct resources
# ---------------------------------------------------------------------------

# AGX1-325 — agent_api_keys
test-api-key:
	$(PYTEST) $(API_KEY_TESTS) -v

test-api-key-create:
	$(PYTEST) tests/test_api_key_create.py -v

test-api-key-get:
	$(PYTEST) tests/test_api_key_get.py -v

test-api-key-list:
	$(PYTEST) tests/test_api_key_list.py -v

test-api-key-delete:
	$(PYTEST) tests/test_api_key_delete.py -v

# AGX1-327 — states delegate to parent task authz
test-state:
	$(PYTEST) $(STATE_TESTS) -v

test-state-list-get:
	$(PYTEST) tests/test_state_list_get.py -v

clean:
	rm -rf $(VENV) .pytest_cache __pycache__
	find . -name __pycache__ -type d -exec rm -rf {} +
	find . -name '*.pyc' -delete
