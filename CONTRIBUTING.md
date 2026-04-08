# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests
```

## Scope

The project is intentionally narrow:

- read-only
- local-first
- citekey-native
- optimized for bounded fulltext retrieval

If you want to propose a broader feature, open an issue first so we can keep the surface area intentional.
