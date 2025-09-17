# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Patch GUI is a Python-based desktop application for applying unified diff patches interactively. It provides both a PySide6 GUI and CLI interface for safely applying patches with fuzzy matching, backup generation, and comprehensive reporting. The project is primarily written in Italian but with English fallback support.

## Common Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/WSL
# .venv\Scripts\activate   # Windows CMD

# Install dependencies
pip install --upgrade pip
pip install .              # CLI only
pip install .[gui]         # CLI + GUI
```

### Running the Application
```bash
# GUI mode (requires gui extra)
patch-gui
# OR
python -m patch_gui

# CLI mode
patch-gui apply --root /path/to/project diff.patch
patch-gui apply --root . --dry-run --threshold 0.90 diff.patch
git diff | patch-gui apply --root . --backup ~/diff_backups -

# Configuration management
patch-gui config show
patch-gui config set threshold 0.95
patch-gui config reset
```

### Testing & Code Quality
```bash
# Run tests
pytest

# Run all pre-commit hooks manually
pre-commit run --all-files

# Install pre-commit hooks (runs on git commit)
pip install pre-commit
pre-commit install
```

### Building & Translations
```bash
# Build translations (automatic during install)
python -m build_translations

# Build distribution package
python -m build
```

## Code Architecture

### High-Level Structure

**Core Components:**
- `patch_gui/app.py` - Main PySide6 GUI application with `MainWindow` class
- `patch_gui/cli.py` - Command-line interface and argument parsing
- `patch_gui/patcher.py` - Core patch application logic with fuzzy matching
- `patch_gui/executor.py` - CLI execution workflow orchestration

**Key Workflows:**
1. **GUI Workflow**: `MainWindow` → `PatchApplyWorker` (threaded) → `apply_hunks`
2. **CLI Workflow**: `run_cli()` → `apply_patchset()` → `apply_hunks`

### Architecture Patterns

**Threading Model:**
- GUI uses `PatchApplyWorker` (QThread) for non-blocking patch application
- Worker emits Qt signals for progress updates and user interaction dialogs
- Main thread handles UI updates and user decision dialogs

**File Resolution Strategy:**
- First tries exact relative path from diff header (cleaning `a/`/`b/` prefixes)
- Falls back to recursive filename search in project root
- Interactive disambiguation when multiple candidates found
- Respects exclude directories (`.git`, `.venv`, `node_modules`, etc.)

**Fuzzy Matching:**
- Uses `difflib.SequenceMatcher` for context similarity scoring
- Configurable threshold (default 0.85) for accepting fuzzy matches
- Interactive candidate selection when multiple viable positions exist

### Configuration System

**Config File:** `~/.patch_gui_config.toml` (TOML format)
**Key Settings:**
- `threshold` - Fuzzy matching threshold (0.5-1.0)
- `exclude_dirs` - Directories to ignore during file search
- `backup_base` - Base directory for backups (default `~/.diff_backups`)
- `log_level` - Logging verbosity
- `dry_run_default` - Default dry-run mode setting
- `write_reports` - Enable/disable report generation

### Internationalization

**Translation System:**
- Qt translations (`.ts`/`.qm` files) for GUI components in `patch_gui/translations/`
- Python gettext for CLI and shared text in `patch_gui/localization.py`
- Supported languages: English (default), Italian
- Language selection via `PATCH_GUI_LANG` environment variable

**Translation Build Process:**
- Source files: `patch_gui_en.ts`, `patch_gui_it.ts`
- Build script: `build_translations.py` (runs `lrelease`/`pyside6-lrelease`)
- Binary `.qm` files generated during package build or runtime compilation

### Backup & Reporting System

**Backup Structure:**
```
~/.diff_backups/
  YYYYMMDD-HHMMSS-fff/          # Timestamped backup directory
    path/to/original/file.ext   # Original file contents
  reports/
    results/
      YYYYMMDD-HHMMSS-fff/      # Matching timestamp
        apply-report.json       # Structured results
        apply-report.txt        # Human-readable summary
```

**Session Tracking:**
- Each patch application creates unique timestamped session
- Tracks per-file and per-hunk success/failure with detailed decisions
- Supports restoration from any backup session via GUI

### Error Handling & Logging

**Logging Configuration:**
- File-based logging with rotation support
- Environment variables: `PATCH_GUI_LOG_LEVEL`, `PATCH_GUI_LOG_FILE`
- Default log file: `~/.patch_gui.log`
- GUI captures logs for real-time display in log panel

**Exception Handling:**
- CLI: Exits with error codes (0=success, 1=failure)
- GUI: Shows error dialogs and continues operation
- Comprehensive error context in reports and logs

## Development Environment Notes

### WSL Compatibility
- Designed for WSL Ubuntu with WSLg for GUI display
- Platform detection in `patch_gui/platform.py`
- WSL-specific Qt High DPI workarounds applied automatically

### Dependencies & Versions
- **Python:** 3.10+ required
- **Core:** `PySide6==6.7.3`, `unidiff==0.7.5`, `charset-normalizer==3.3.2`
- **Dev Tools:** `mypy`, `black`, `ruff`, `pytest`, `pre-commit`
- Package management via setuptools with optional GUI dependencies

### Testing Strategy
- Unit tests in `tests/` directory using pytest
- Test coverage for core patching logic, CLI parsing, and configuration
- GUI testing limited due to Qt interaction complexity
- Pre-commit hooks ensure code quality (formatting, linting, type checking)

### File Structure Patterns
- **Main modules:** Single responsibility with clear separation of concerns
- **Utilities:** Common functions in `utils.py` (path handling, encoding, text processing)
- **Type hints:** Comprehensive typing throughout codebase with mypy strict mode
- **Error types:** Custom exception classes for different failure scenarios

This architecture enables reliable patch application with comprehensive user feedback and error recovery mechanisms.