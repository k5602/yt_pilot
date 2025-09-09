# YouTube Pilot - GitHub Copilot Instructions

**Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

YouTube Pilot (yt_pilot) is a high-performance Python YouTube downloader utility with parallel downloads, quality selection, playlist support, captions, resume functionality, and comprehensive reporting. Built on yt-dlp with a modular architecture.

## Working Effectively

### Bootstrap and Install
- **REQUIRED**: Python 3.11+ is required (repository uses Python 3.12)
- Install package with development dependencies:
  ```bash
  pip install .[dev]
  ```
  Takes ~30 seconds. NEVER CANCEL - wait for completion.
- **NETWORK LIMITATION**: Installation may fail due to network timeouts to PyPI in some environments
  - **WORKAROUND**: If installation fails, you can still run the application directly:
    ```bash
    python main.py --help
    ```
- After successful installation, `yt-downloader` console script is available in PATH
- Alternative entry point: `python main.py [args]` (works without installation)

### Testing
- **DEPENDENCY**: Testing requires successful installation via `pip install .[dev]`
- Run core tests (recommended): 
  ```bash
  pytest -q -m "not contract"
  ```
  Takes ~0.5 seconds. All tests should pass.
- Run all tests (includes 2 known failing contract tests):
  ```bash
  pytest -q
  ```
  Takes ~1 second. 30+ tests pass, 2 contract tests fail due to missing schema files - this is expected.
- Test markers available: `unit`, `integration`, `contract`, `network`
- Contract tests fail because `specs/001-refactor-app-into/contracts/report-schema.json` is missing
- **FALLBACK**: If installation fails, skip testing and use direct Python execution for validation

### Code Quality
- Basic Python syntax checking works:
  ```bash
  python -m py_compile main.py yt_downloader/*.py
  ```
- No advanced linting tools (flake8, black, pylint) are configured in the project
- Always run syntax check before committing changes

### Application Testing
- Test basic functionality with dry-run (no actual downloads):
  ```bash
  yt-downloader --dry-run "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  ```
  OR using direct Python entry point:
  ```bash
  python main.py --dry-run "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  ```
- Test with JSON output:
  ```bash
  yt-downloader --dry-run --report-format json "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  ```
- Test audio-only mode:
  ```bash
  yt-downloader --dry-run -a "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  ```
- All basic functionality tests complete in <5 seconds each

## Build Process

### Package Building
- **ISSUE**: `python -m build` fails due to network timeouts in isolated environment
- **WORKAROUND**: Use `pip install .[dev]` instead for development
- Building requires: `pip install build` first, but isolated environment pip calls timeout
- For wheel distribution, building may work in environments with better network connectivity

## Validation Scenarios

Always test these scenarios after making changes:

### Core Functionality Test
1. Try to install package: `pip install .[dev]` (may fail due to network timeouts)
2. Test help via console script (if installed): `yt-downloader --help` 
3. **ALWAYS** test help via Python entry point: `python main.py --help` (should show full usage)
4. Test dry-run: `python main.py --dry-run "https://www.youtube.com/watch?v=dQw4w9WgXcQ"`
5. Test JSON output: `python main.py --dry-run --report-format json "URL"`
6. Run core tests (if package installed): `pytest -q -m "not contract"`

### Extended Functionality Test
1. Test audio mode: `python main.py --dry-run -a "URL"`
2. Test filtering: `python main.py --dry-run --filter "test" "URL"`
3. Test quality selection: `python main.py --dry-run -q 1080p "URL"`
4. Test captions: `python main.py --dry-run --captions --captions-auto "URL"`
5. Test naming template: `python main.py --dry-run --naming-template "{index:03d}-{title}" "URL"`

## Architecture Overview

### Key Modules (yt_downloader/)
- `cli.py`: Command-line interface and argument parsing
- `config.py`: AppConfig dataclass with runtime configuration
- `downloader.py`: Core download orchestration
- `models.py`: Data structures (VideoItem, CaptionTrack)
- `manifest.py`: Resume functionality via JSON manifest
- `captions.py`: Manual and automatic caption handling
- `filtering.py`: Title filtering and index range slicing
- `naming.py`: Filename template expansion
- `reporting.py`: Structured summary generation
- `plugins.py`: Plugin manager for extensibility
- `planner.py`: Dry-run planning (placeholder for future expansion)
- `logging_utils.py`: Central logger factory

### Project Structure
```
/home/runner/work/yt_pilot/yt_pilot/
├── README.md                 # Main documentation
├── LICENSE                   # MIT license
├── pyproject.toml            # Modern Python packaging config
├── pytest.ini               # Test configuration
├── main.py                   # Alternative entry point
├── docs/                     # Documentation
│   ├── architecture.md       # Detailed architecture overview
│   └── sample-report.json    # Example report structure
├── yt_downloader/           # Main package (13 modules)
└── tests/                   # Test suite
    ├── unit/                # Unit tests
    ├── integration/         # Integration tests
    └── contract/            # Contract tests (2 fail due to missing schema)
```

## Common Tasks

### Development Workflow
1. Try to run `pip install .[dev]` after fresh clone (may fail due to network issues)
2. **ALWAYS** verify functionality using: `python main.py --help`
3. Make changes to code
4. Run `python -m py_compile` for syntax check
5. Test functionality with dry-run commands using `python main.py`
6. Run `pytest -q -m "not contract"` to verify tests pass (if package installed)
7. **FALLBACK**: If installation fails, rely on direct Python execution for all testing

### Adding New Features
1. Follow modular architecture - add new functionality to appropriate module
2. Add unit tests in `tests/unit/`
3. Update `tests/integration/` if cross-module functionality
4. Test with dry-run scenarios before real downloads
5. Update documentation if external API changes

### Debugging Issues
1. Use dry-run mode for testing without network calls
2. Check logs - application uses structured logging
3. Test individual modules with unit tests
4. Use `python main.py` vs `yt-downloader` to compare entry points

## Dependencies and Requirements

### Core Dependencies
- `yt-dlp>=2025.9.5` - YouTube download engine
- `youtube-transcript-api>=1.2.2` - Caption handling
- `rich>=14.1.0` - Terminal formatting and output

### Development Dependencies  
- `pytest>=8.0.0` - Test framework
- `jsonschema>=4.21.0` - Schema validation

### System Requirements
- Python 3.11+ (tested with 3.12)
- No additional system dependencies

## Known Issues

1. **Package Installation May Fail**: `pip install .[dev]` may timeout due to network issues connecting to PyPI
   - **Impact**: Cannot install console script `yt-downloader`
   - **Workaround**: Use `python main.py [args]` as alternative entry point

2. **Package Build Fails**: `python -m build` times out due to network issues in isolated pip environment
   - **Impact**: Cannot create distributable wheels in this environment
   - **Workaround**: Use `pip install .[dev]` for development when network allows

3. **Contract Test Failures**: 2 tests fail due to missing schema file
   - **File**: `specs/001-refactor-app-into/contracts/report-schema.json`
   - **Impact**: Contract validation tests cannot run
   - **Workaround**: Use `pytest -q -m "not contract"` to skip these tests

4. **No Advanced Linting**: Project lacks flake8, black, pylint configuration
   - **Impact**: Only basic syntax checking available
   - **Workaround**: Use `python -m py_compile` for syntax validation

## Time Expectations

- **NEVER CANCEL** any commands - all operations complete quickly:
  - Installation: ~30 seconds
  - Tests (core): ~0.5 seconds  
  - Tests (all): ~1 second
  - Functionality tests: <5 seconds each
  - Syntax checking: <1 second

No operations require extended timeouts - all core development tasks complete rapidly.