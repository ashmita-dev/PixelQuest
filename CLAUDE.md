# CLAUDE.md

Guidance for AI assistants working on Pixel Quest.

## Commands (Windows, from repo root)

- Run: `.venv\Scripts\python main.py` (`--keyboard`, `--camera synthetic`, `--diag`)
- Tests: `.venv\Scripts\python -m pytest -q` (headless; never opens a webcam)
- Headless smoke run: set `SDL_VIDEODRIVER=dummy`, then `python main.py --keyboard --frames 120 --screenshot out.png`
- Regenerate synthetic samples/figures: `python scripts/generate_samples.py`
- Regenerate screenshots: `python scripts/capture_screenshots.py`
- Rebuild report DOCX/PDF: `python scripts/build_report.py` (PDF needs MS Word)

## Architecture

- `src/vision.py` holds pure, tested functions (`preprocess`, `segment_hsv`, `clean_mask`, `find_marker`, …),
  composed by `process_frame`. `VisionTracker` runs them on a daemon thread, and the game polls `snapshot()`.
- `src/session.py` holds the game rules, with no drawing or input, and returns `Event`s. `src/game.py` turns events into effects.
- All tunables live in `src/config.py`.

## Rules

- Tests must not require a webcam. Use `SyntheticSource`, fake sources or `source_factory=lambda: None`.
- Call `ui.reset_caches()` around `pygame.quit()`/re-init, because cached Fonts crash after quit.
- Docs must stay honest: list only algorithms that exist, label synthetic data as synthetic, and
  never claim webcam results that were not observed. Update `docs/IVP_MAPPING.md` when the pipeline changes.
