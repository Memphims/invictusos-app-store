# InvictusOS Store

A Tkinter desktop package browser for APT-based systems, currently targeting InvictusOS Sagaris.

## Requirements

- Python 3.10 or newer
- Tkinter from the system Python packages (for Debian-based systems: `python3-tk`)
- APT tools (`apt-cache`, `apt-get`, and `dpkg-query`)
- `pkexec` and PolicyKit for privileged package changes

The application has no third-party runtime Python dependencies. Its current popular-app list uses Debian Popularity Contest data when available, so those rankings are a placeholder until Sagaris has its own catalog data.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m invictusos_store
```

Run the tests with:

```bash
python -m pytest
```

## Project layout

```text
src/invictusos_store/
  domain/       Package data and catalog definitions
  ui/           Tkinter window and reusable widgets
  __main__.py   Module entry point
 tests/         Automated tests
```

## Current scope

Package discovery and installation use APT and dpkg directly. Test changes with mocked commands where possible; installing or removing packages should only be tested in a disposable Sagaris environment.
