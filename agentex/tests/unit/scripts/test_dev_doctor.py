"""Tests for scripts/agentex_dev_doctor.py"""

import unittest
from unittest import mock

from scripts.agentex_dev_doctor import _check_docker_registry_env, _port_free


class TestAgentexDevDoctor(unittest.TestCase):
    def test_registry_unset_passes(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            gate = _check_docker_registry_env()
        self.assertTrue(gate["passed"])

    def test_private_ecr_fails(self):
        env = {"DOCKER_REGISTRY": "022465994601.dkr.ecr.us-west-2.amazonaws.com/golden/"}
        with mock.patch.dict("os.environ", env, clear=True):
            gate = _check_docker_registry_env()
        self.assertFalse(gate["passed"])

    def test_port_free_helper(self):
        self.assertIsInstance(_port_free(59999), bool)


if __name__ == "__main__":
    unittest.main()
