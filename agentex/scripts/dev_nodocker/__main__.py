"""Entry point: `python -m scripts.dev_nodocker` (used by `./dev.sh no-docker` / `make dev-no-docker`)."""

from scripts.dev_nodocker.runner import main

if __name__ == "__main__":
    main()
