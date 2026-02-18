# Papman Agent Notes

## Discovery Defaults

- Start with code roots only:
  - `src/` for application code
  - `tests/` when present
- Do not scan environment/tooling folders unless explicitly requested:
  - `.venv/`, `.git/`, `.idea/`, `__pycache__/`, `build/`, `dist/`
- Prefer:
  - `scripts/code-search "<pattern>" src` for text
  - `find src -type f` for file lists

## Why

- Recursive fallback search (`grep -R`, broad `find .`) can be slow and noisy.
- Large local artifacts and virtualenv packages dominate scan time and output.
