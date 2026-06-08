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
API_KEY_TESTS := tests/test_api_key_create.py tests/test_api_key_get.py tests/test_api_key_list.py tests/test_api_key_delete.py
EVENT_TESTS   := tests/test_event_authz.py

# Aggregate groupings — extend these as resources are added.
DIRECT_RESOURCE_TESTS := $(API_KEY_TESTS)
# Future direct-resource additions go here:
#   DIRECT_RESOURCE_TESTS += $(AGENT_TESTS) $(TASK_TESTS)

SUB_RESOURCE_TESTS := $(EVENT_TESTS)
# Future sub-resource additions go here:
#   SUB_RESOURCE_TESTS += $(STATE_TESTS) $(MESSAGE_TESTS) $(TRACKER_TESTS) $(CHECKPOINT_TESTS)

.PHONY: install test \
        test-direct-resources test-sub-resources \
        test-api-key test-api-key-create test-api-key-get test-api-key-list test-api-key-delete \
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
	@echo "  make test-direct-resources   resources with their own SpiceDB type"
	@echo "  make test-sub-resources      resources that delegate to a parent"
	@echo ""
	@echo "Run one resource:"
	@echo "  make test-api-key            all AGX1-325 cases"
	@echo "  make test-event              all AGX1-331 cases"
	@echo ""
	@echo "Run one case:"
	@echo "  make test-api-key-{create,get,list,delete}"

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
