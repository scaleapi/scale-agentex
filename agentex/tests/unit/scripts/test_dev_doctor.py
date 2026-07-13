"""Tests for scripts/agentex_dev_doctor.py"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

_MODULE_PATH = Path(__file__).resolve().parents[4] / "scripts" / "agentex_dev_doctor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("agentex_dev_doctor", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["agentex_dev_doctor"] = module
    spec.loader.exec_module(module)
    return module


agentex_dev_doctor = _load_module()


class TestAgentexDevDoctor(unittest.TestCase):
    def test_registry_unset_passes(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            gate = agentex_dev_doctor._check_docker_registry_env()
        self.assertTrue(gate["passed"])

    def test_private_ecr_fails(self):
        env = {"DOCKER_REGISTRY": "022465994601.dkr.ecr.us-west-2.amazonaws.com/golden/"}
        with mock.patch.dict("os.environ", env, clear=True):
            gate = agentex_dev_doctor._check_docker_registry_env()
        self.assertFalse(gate["passed"])

    def test_port_free_helper(self):
        self.assertIsInstance(agentex_dev_doctor._port_free(59999), bool)


if __name__ == "__main__":
    unittest.main()
