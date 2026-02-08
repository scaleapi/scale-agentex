#!/usr/bin/env python3
"""
Docker environment detection and setup for testcontainers.
Handles Docker Desktop, Rancher Desktop, Colima, and Podman configurations.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def detect_docker_environment():
    """Detect which Docker environment is being used."""
    print("🔍 Detecting Docker environment...")

    # 1️⃣ Prefer Rancher Desktop if its socket exists
    rd_socket = Path.home() / ".rd" / "docker.sock"
    if rd_socket.exists():
        print("✅ Detected: Rancher Desktop")
        return "rancher_desktop"

    # 2️⃣ Prefer Colima if its socket exists
    colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
    if colima_socket.exists():
        print("✅ Detected: Colima")
        return "colima"

    # 3️⃣ Check if the Docker daemon is available (this should cover most CI runners)
    try:
        result = subprocess.run(
            ["docker", "version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ Detected: Docker daemon is running")
            return "docker_desktop"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 4️⃣ If docker CLI isn't available or daemon isn't running, fall back to Podman detection
    if shutil.which("podman"):
        print("✅ Detected: Podman")
        return "podman"

    # 5️⃣ Attempt docker context show as last resort (older Docker versions)
    try:
        result = subprocess.run(
            ["docker", "context", "show"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and "desktop" in result.stdout.lower():
            print("✅ Detected: Docker Desktop (via context)")
            return "docker_desktop"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # If all checks failed
    print("❌ Could not detect Docker environment")
    return "unknown"


def setup_docker_environment(environment_type):
    """Set up environment variables for the detected Docker environment."""
    env_vars = {}

    if environment_type == "rancher_desktop":
        print("🔧 Setting up Rancher Desktop environment...")
        env_vars.update(
            {
                "DOCKER_HOST": f"unix://{Path.home()}/.rd/docker.sock",
                "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE": "/var/run/docker.sock",
            }
        )

        # Try to get the host override for Rancher Desktop
        try:
            result = subprocess.run(
                ["rdctl", "shell", "ip", "a", "show", "vznat"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Parse the IP from the output using awk-like logic
                for line in result.stdout.split("\n"):
                    if "inet " in line and "/" in line:
                        ip = line.strip().split()[1].split("/")[0]
                        env_vars["TESTCONTAINERS_HOST_OVERRIDE"] = ip
                        break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(
                "⚠️  Could not get Rancher Desktop host IP, continuing without TESTCONTAINERS_HOST_OVERRIDE"
            )

    elif environment_type == "colima":
        print("🔧 Setting up Colima environment...")
        env_vars.update(
            {
                "DOCKER_HOST": f"unix://{Path.home()}/.colima/default/docker.sock",
                "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE": "/var/run/docker.sock",
            }
        )

        # Try to get Colima IP address
        try:
            result = subprocess.run(
                ["colima", "ls", "-j"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import json

                data = json.loads(result.stdout)
                if data and "address" in data:
                    env_vars["TESTCONTAINERS_HOST_OVERRIDE"] = data["address"]
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            print(
                "⚠️  Could not get Colima host IP, continuing without TESTCONTAINERS_HOST_OVERRIDE"
            )

    elif environment_type == "podman":
        print("🔧 Setting up Podman environment...")

        # Check if we're on macOS or Linux
        import platform

        if platform.system() == "Darwin":  # macOS
            try:
                result = subprocess.run(
                    [
                        "podman",
                        "machine",
                        "inspect",
                        "--format",
                        "{{.ConnectionInfo.PodmanSocket.Path}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    socket_path = result.stdout.strip()
                    env_vars["DOCKER_HOST"] = f"unix://{socket_path}"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        else:  # Linux
            xdg_runtime_dir = os.environ.get(
                "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"
            )
            env_vars["DOCKER_HOST"] = f"unix://{xdg_runtime_dir}/podman/podman.sock"

        env_vars.update(
            {
                "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE": "/var/run/docker.sock",
                "TESTCONTAINERS_RYUK_DISABLED": "true",  # Podman often needs Ryuk disabled
            }
        )

    elif environment_type == "docker_desktop":
        print("🔧 Docker Desktop detected - using default configuration")
        # Docker Desktop usually works out of the box, no special env vars needed
        pass

    else:
        print("❌ Unknown Docker environment - you may need to configure manually")
        return False

    # Set the environment variables
    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"   {key}={value}")

    return True


def validate_testcontainers_setup():
    """Validate that testcontainers can work with the current Docker setup."""
    print("🧪 Validating testcontainers setup...")

    try:
        # Try to import testcontainers
        from testcontainers.core.generic import DockerContainer

        # Try to create a simple container to test connectivity
        # Use alpine with a simple command that will work
        with DockerContainer("alpine:latest").with_command("sleep 1") as container:
            container.start()
            print("✅ Testcontainers setup is working!")
            return True

    except ImportError:
        print(
            "❌ testcontainers not installed. Run 'uv sync --group test' to install test dependencies."
        )
        return False
    except Exception as e:
        print(f"❌ Testcontainers validation failed: {e}")
        print(
            "💡 This might be expected if Docker isn't running or configured properly"
        )
        print(
            "💡 Try running 'docker run --rm alpine:latest echo test' manually to verify Docker works"
        )
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Set up Docker environment for testcontainers"
    )
    parser.add_argument(
        "--check-docker",
        action="store_true",
        help="Check and validate Docker environment setup",
    )
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Set up environment without validation",
    )

    args = parser.parse_args()

    if args.check_docker:
        environment = detect_docker_environment()
        if environment == "unknown":
            print("\n💡 Troubleshooting tips:")
            print("   - Make sure Docker/Rancher Desktop/Colima is running")
            print("   - Try running 'docker version' to test connectivity")
            print("   - Check if you need to start your Docker environment")
            sys.exit(1)

        setup_success = setup_docker_environment(environment)
        if not setup_success:
            sys.exit(1)

        if not validate_testcontainers_setup():
            sys.exit(1)

        print("\n🎉 Docker environment is ready for testing!")
        return

    # Default behavior: detect and setup environment
    environment = detect_docker_environment()
    if environment == "unknown":
        print("❌ Could not detect Docker environment")
        sys.exit(1)

    setup_success = setup_docker_environment(environment)
    if not setup_success:
        sys.exit(1)

    if not args.setup_only:
        if not validate_testcontainers_setup():
            sys.exit(1)


if __name__ == "__main__":
    main()
