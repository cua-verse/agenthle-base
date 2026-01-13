# Contributing to Agenthle

Thank you for your interest in contributing to Agenthle! This guide will help you get started with contributing to the project.

## Code Style and Standards

We follow these code style and standards:

- **Python**: We use Black for code formatting, isort for import sorting, and Ruff for linting.
  - Run `uv run black .` to format your code
  - Run `uv run isort .` to sort imports
  - Run `uv run ruff check .` to check for linting errors

- **Commits**: Use clear and descriptive commit messages
  - Start with a short summary (50 characters or less)
  - Add a more detailed description if needed
  - Reference issues if applicable

## Development Workflow

### 1. Fork and Clone the Repository

First, fork the repository on GitHub, then clone it to your local machine:

```bash
git clone git@github.com:your-username/agenthle.git
cd agenthle
git submodule update --init --recursive
```

### 2. Create a Branch

Create a new branch for your changes:

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/` for new features
- `fix/` for bug fixes
- `docs/` for documentation changes
- `refactor/` for code refactoring

### 3. Make Changes

Make your changes to the codebase. Remember to:
- Follow the code style guidelines
- Write clear and concise code
- Update documentation if necessary

### 4. Test Your Changes

While we don't have an extensive test suite yet, please test your changes manually to ensure they work as expected.

### 5. Commit Your Changes

Commit your changes with a clear commit message:

```bash
git add .
git commit -m "Add feature: your feature description"
```

### 6. Push to Your Fork

Push your changes to your forked repository:

```bash
git push origin feature/your-feature-name
```

### 7. Create a Pull Request

Go to the original repository on GitHub and create a pull request:
- Provide a clear title and description
- Explain what changes you made and why
- Reference any related issues

## Code Review Process

- All pull requests will be reviewed by project maintainers
- Reviewers may ask for changes or clarifications
- Once approved, your changes will be merged into the main branch

## Environment Configuration

We use `.env` files for configuration. Make sure to:
- Use `.env.template` as a base for your `.env` file
- Never commit actual `.env` files to the repository
- Add `.env` to your `.gitignore` file if it's not already there

## Contact

If you have any questions or need help, please feel free to reach out to the project maintainers.

Thank you for contributing to Agenthle!