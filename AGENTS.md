# Repository Guidelines

## Project Structure & Module Organization
- Top-level scripts and utilities live in `utils/` (one-off API helpers).
- Bot-specific workflows live in `my-*-bot/` directories, each with its own runner scripts and configs.
- Documentation lives in `README.md` and `API.md`.
- Runtime outputs are commonly written to `data/` (git-ignored in `.gitignore`).

## Build, Test, and Development Commands
There is no build step; run scripts directly with Python or whatever is used. 
- Example utility run: `python utils/poly_data_get_user_balance.py 0xYourWallet`
- Example sports bot run: `python my-sports-bot/get_nfl_markets.py`
- Example cron runners:
  - `bash my-creamster-monitor-bot/run.sh`
  - `bash my-openai-whale-bot/run.sh`
  - `bash my-sports-bot/run_monitor_game_holders.sh`

## Coding Style & Naming Conventions
- Python 3 scripts, 4-space indentation, and snake_case filenames.
- Keep scripts CLI-friendly: accept args via `sys.argv` when needed, or read from `.env`.
- Environment variables use uppercase names (e.g., `PUSHOVER_API_TOKEN`).

## Testing Guidelines
- Validate changes by running the affected script with a small, known input or short polling window.

## Configuration & Secrets
- Some bots read `.env` files in their own directories for Pushover credentials.
- Keep secrets out of the repo; store local files alongside the bot script if needed.

## Agent-Specific Instructions
- When adding or updating Polymarket API usage, consult the official docs directly, use only the exact flags/code shown there (no guess-and-check), never hallucinate, and cite the reference links you used.
- If a script changes materially, update `README.md` to reflect the new or modified behavior.
- For quick endpoint reference, see `API.md`.
