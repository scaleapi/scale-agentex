# Contributing to Agentex

Thank you for considering contributing to Agentex! Contributions make the open source community amazing and help improve the project for everyone. Any contributions you make are **greatly appreciated**.

We welcome bug fixes, enhancements, documentation improvements, tests, and more.

---

## Development Environment Setup

To set up your development environment for Agentex, please refer to the [README.md](./README.md) for up-to-date instructions.

---

## How to Contribute

1. **Fork** the repository.
2. **Clone** your fork:
    ```bash
    git clone https://github.com/<your-username>/agentex.git
    cd agentex
    ```
3. **Set the original repo as upstream** (recommended):
    ```bash
    git remote add upstream https://github.com/scaleapi/agentex.git
    ```
4. **Create a new branch** for your feature or bugfix:
    ```bash
    git checkout -b my-feature-or-bugfix
    ```
5. **Make your changes.**  
   Follow project coding style and conventions.
6. **Test your changes:**
    ```bash
    make test
    ```
    Run linter/formatter as required:
    ```bash
    make lint
    ```
7. **Commit your changes** (see commit message guidelines below).
8. **Push** to your fork:
    ```bash
    git push origin my-feature-or-bugfix
    ```
9. **Open a Pull Request** against `main` with a clear description.

---

## Best Practices for Writing Commit Messages

- **Separate subject from body with a blank line**.
- **Limit the subject line to 50 characters**.
- **Capitalize the subject line**.
- **Do not end the subject line with a period**.
- **Use the imperative mood in the subject line**  
  (e.g., “Fix bug” not “Fixed bug” or “Fixes bug”).
- **Wrap the body at 72 characters**.
- **Use the body to explain what and why vs. how** (if needed).
- **Reference relevant issues/PRs** (e.g., `Fixes #123`).

**Example:**
```
Add user authentication middleware

This middleware intercepts requests to check authentication tokens
and ensures only valid users can access protected routes.

Fixes #42
```

For more, see: [Chris Beams' guide to writing great commit messages](https://cbea.ms/git-commit/).

---

## Contributing to the Python SDK

If you want to contribute to the Agentex Python SDK, please use the [scale-agentex-python repository](https://github.com/scaleapi/scale-agentex-python) and follow its contributing guidelines.

---

## Code of Conduct

Be respectful and considerate. By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md) (if present).

---

## Need Help?

If you have any questions, please open an issue or join the discussion on GitHub. We're happy to help!
