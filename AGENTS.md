# Repository Guidelines

## Coding Style & Naming Conventions
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
