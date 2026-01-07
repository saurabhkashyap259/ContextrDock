<!--
SYNC IMPACT REPORT
==================
Version: 0.0.0 → 1.0.0
Bump Rationale: MAJOR - Initial constitution establishment for ContextDock Python project

Modified Principles:
  - Added: I. Strict Test-Driven Development (TDD)
  - Added: II. Virtual Environment Isolation (.venv)
  - Added: III. Type Safety & Static Analysis
  - Added: IV. Pytest Testing Framework
  - Added: V. Code Quality & Formatting
  - Added: VI. Dependency Management
  - Added: VII. Simplicity & YAGNI

Added Sections:
  - Python Tooling Standards
  - Development Workflow & Quality Gates

Removed Sections: None (initial creation)

Templates Requiring Updates:
  ✅ plan-template.md - Updated constitution check references
  ✅ spec-template.md - Aligned with TDD acceptance criteria format
  ✅ tasks-template.md - Updated test-first task ordering

Follow-up TODOs: None
-->

# ContextDock Constitution

## Core Principles

### I. Strict Test-Driven Development (TDD) - NON-NEGOTIABLE

**All code MUST follow the Red-Green-Refactor cycle without exception:**
- Write failing tests FIRST based on acceptance criteria
- Tests MUST fail for the right reason before implementation
- Implement ONLY enough code to make tests pass
- Refactor with test coverage protection
- NO production code without corresponding tests
- Test approval from stakeholders REQUIRED before implementation

**Rationale**: TDD ensures correctness, prevents regressions, and maintains a living specification. Tests document behavior and enable fearless refactoring. This is the foundation of all development in ContextDock.

### II. Virtual Environment Isolation (.venv)

**All Python development MUST use .venv virtual environments:**
- Project MUST maintain a `.venv/` directory in repository root
- All dependency installations MUST occur within `.venv`
- `.venv/` MUST be excluded from version control (in .gitignore)
- Development commands MUST activate `.venv` before execution
- CI/CD pipelines MUST create fresh `.venv` for reproducibility
- NO system-wide package installations allowed for project dependencies

**Rationale**: Virtual environment isolation prevents dependency conflicts, ensures reproducible builds across environments, and maintains clean separation between project dependencies and system packages.

### III. Type Safety & Static Analysis

**Python code MUST be statically typed and analyzed:**
- Type hints REQUIRED for all function signatures (parameters and return types)
- `mypy` MUST pass in strict mode with no errors
- Type annotations MUST be meaningful, not `Any` bypasses
- Generic types and protocols SHOULD be used where appropriate
- Static analysis MUST run before tests in CI/CD pipeline

**Rationale**: Type hints catch bugs before runtime, improve IDE support, serve as inline documentation, and enable safer refactoring. They bring many benefits of static languages to Python.

### IV. Pytest Testing Framework

**All tests MUST use pytest conventions and best practices:**
- Test files MUST follow `test_*.py` or `*_test.py` naming
- Test functions MUST be prefixed with `test_`
- Fixtures SHOULD be used for shared test setup
- Parametrized tests SHOULD be used for multiple similar cases
- Tests MUST be organized: `tests/unit/`, `tests/integration/`, `tests/contract/`
- Assertions MUST use pytest's rich assertion introspection (not unittest-style)
- Coverage reports REQUIRED (minimum 80% line coverage for new code)

**Rationale**: Pytest provides superior test discovery, fixtures, parametrization, and assertion messages. Consistent testing structure improves maintainability and team collaboration.

### V. Code Quality & Formatting

**Code MUST adhere to Python quality standards:**
- `ruff` MUST be used for linting and formatting (replaces flake8, black, isort)
- Code MUST pass `ruff check .` with no violations
- Line length MUST NOT exceed 100 characters
- Imports MUST be organized: stdlib → third-party → local
- Docstrings REQUIRED for all public modules, classes, and functions
- Follow PEP 8 style guide principles
- NO commented-out code in commits

**Rationale**: Consistent formatting eliminates style debates, improves readability, and reduces cognitive load. Automated tooling ensures standards are enforced uniformly.

### VI. Dependency Management

**Dependencies MUST be managed with precision and justification:**
- `requirements.txt` MUST pin exact versions (`package==x.y.z`)
- `requirements-dev.txt` MUST contain development-only dependencies
- New dependencies REQUIRE justification in PR description
- Dependency updates MUST include changelog review and testing
- `pip-tools` SHOULD be used for dependency compilation when complexity grows
- Security vulnerabilities MUST be addressed within 7 days of disclosure

**Rationale**: Pinned dependencies ensure reproducible builds. Explicit dev dependencies keep production images lean. Justified additions prevent bloat.

### VII. Simplicity & YAGNI (You Aren't Gonna Need It)

**Code MUST remain as simple as possible:**
- Implement ONLY what is specified in current requirements
- Reject premature optimization and speculative generality
- Prefer explicit code over clever abstractions
- Delete unused code immediately (tests prove it's unused)
- Each function/class SHOULD have a single, clear responsibility
- Complexity MUST be justified in writing before implementation

**Rationale**: Simple code is easier to understand, test, modify, and debug. YAGNI prevents waste and keeps the codebase maintainable. Tests provide safety for simple solutions.

## Python Tooling Standards

**Required Development Tools:**
- Python 3.11+ (leverage latest language features and performance)
- pytest 7.4+ (testing framework)
- mypy 1.0+ (static type checking)
- ruff 0.1+ (linting and formatting)
- Coverage.py (code coverage reporting)

**Tooling Configuration:**
- All tool configurations MUST be in `pyproject.toml` when possible
- Alternative: `.ruff.toml`, `mypy.ini` only if `pyproject.toml` inadequate
- Configuration MUST be committed to version control
- CI/CD MUST use identical tool versions as local development

**Pre-commit Checks (Recommended):**
```bash
ruff check .
mypy .
pytest tests/
```

## Development Workflow & Quality Gates

**Feature Development Cycle:**
1. **Specification**: Write acceptance criteria in spec.md (Given-When-Then format)
2. **Test Writing**: Convert acceptance criteria to failing pytest tests
3. **Test Review**: Stakeholder approves tests match requirements
4. **Implementation**: Write minimal code to pass tests (Red → Green)
5. **Refactor**: Improve code structure while maintaining green tests
6. **Quality Gates**: Run ruff, mypy, pytest with coverage
7. **Code Review**: Peer review with constitution compliance check

**Quality Gates (MUST pass before merge):**
- ✅ All pytest tests pass (`pytest tests/`)
- ✅ Type checking passes (`mypy .`)
- ✅ Linting passes (`ruff check .`)
- ✅ Formatting correct (`ruff format --check .`)
- ✅ Test coverage ≥ 80% for new code
- ✅ No security vulnerabilities in dependencies
- ✅ Constitution compliance verified

**Pull Request Requirements:**
- PR description MUST reference spec.md and acceptance criteria
- Tests MUST be included and demonstrate Red-Green-Refactor
- Type hints MUST be present for new functions
- Documentation updated if public API changed
- Dependency changes MUST be justified
- Breaking changes MUST be marked MAJOR version bump

## Governance

**Constitutional Authority:**
- This constitution supersedes all other development practices
- All code reviews MUST verify constitutional compliance
- Violations MUST be justified in writing and approved by technical lead
- Continuous violations trigger constitution review

**Amendment Process:**
- Amendments REQUIRE written proposal with rationale
- MAJOR version bump for backward-incompatible governance changes
- MINOR version bump for new principles or material expansions
- PATCH version bump for clarifications and wording improvements
- All amendments MUST update dependent templates and documentation

**Compliance Enforcement:**
- Automated checks via CI/CD pipeline for tooling compliance
- Manual review for TDD adherence and principle violations
- Constitution violations block PR merges
- Systematic violations trigger team constitution review session

**Living Document:**
- Constitution reviewed quarterly for relevance and effectiveness
- Feedback collected from all team members
- Amendments batched and proposed with version bump rationale

**Version**: 1.0.0 | **Ratified**: 2026-01-06 | **Last Amended**: 2026-01-06
