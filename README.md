# Agent Reach — upstream evaluation fork

[![Upstream](https://img.shields.io/badge/upstream-Panniantong%2FAgent--Reach-0969da)](https://github.com/Panniantong/Agent-Reach)
[![CI](https://github.com/MiMindMendinc/Agent-Reach/actions/workflows/pytest.yml/badge.svg)](https://github.com/MiMindMendinc/Agent-Reach/actions/workflows/pytest.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-3776AB.svg)](pyproject.toml)

This repository is a public fork of
[Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach), retained
for dependency evaluation and compatibility testing with local AI-agent
workflows.

**Michigan MindMend Inc. does not claim original authorship of Agent Reach.**
The upstream maintainers own the project direction, documentation, releases,
and support channels. Use the
[upstream repository](https://github.com/Panniantong/Agent-Reach) for current
installation instructions, issues, and releases.

## Why this fork remains public

GitHub requires forks of public repositories to remain in the public fork
network. The visibility of this fork cannot be changed independently.

The fork is kept as a transparent, reproducible evaluation surface:

- the upstream source and attribution remain intact;
- the included CI runs the upstream test suite on Python 3.10–3.13;
- the wheel gate checks packaging and required skill assets;
- local portfolio work is not mixed into this repository.

## Verification

```bash
git clone https://github.com/MiMindMendinc/Agent-Reach.git
cd Agent-Reach
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -c constraints.txt -e ".[dev]"
pytest -q
```

The latest cleanup audit is recorded in [FORK_AUDIT.md](FORK_AUDIT.md).

## Boundaries

- This is not a Michigan MindMend product.
- No upstream capability is presented as original portfolio work.
- Credentials, cookies, tokens, and private configuration must never be
  committed.
- Live third-party platform behavior can change independently of this fork.

## Upstream documentation

- [English documentation](https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md)
- [Installation guide](https://github.com/Panniantong/Agent-Reach/blob/main/docs/install.md)
- [Security policy](https://github.com/Panniantong/Agent-Reach/blob/main/SECURITY.md)
- [License](LICENSE)
