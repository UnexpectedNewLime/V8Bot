# Agent Rules

## Always Read First

Before changing code or docs, read:

- `docs/00-read-this-first.md`
- `docs/08-style-guide.md`
- `docs/09-engineering-principles.md`

## Never

- Never bypass the service layer.
- Never write business logic in Discord commands.
- Never mix scraping with persistence.
- Never let scrapers know about Discord or the database.
- Never introduce new architecture patterns without updating docs first.
- Never implement non-MVP features unless explicitly asked.

## Feature Work

- If architecture changes, update docs first.
- Then implement code.
- Keep changes small and aligned with existing docs.
- Prefer the documented design over inventing a new one.

## When Unsure

- Prefer the simpler implementation.
- Prefer explicit over implicit.
- Prefer deterministic behaviour over cleverness.
- Ask only when a safe assumption is not possible.

## Code Quality

- Type hints are required.
- Tests are required for new logic.
- Core logic must be testable without Discord.
- Tests must not require live network calls.

## Scope Discipline

- Stay inside MVP scope.
- Do not add real website scraping unless explicitly requested.
- Do not add a web dashboard yet.
- Do not add real-time alerts.
- Do not turn the bot into a reusable plugin.

## Scraper Rules

- Never scrape Facebook Marketplace in MVP.
- Do not bypass anti-bot protections.
- Respect rate limits.
- Scraper failures are expected and must be handled gracefully.
- Source tests must not create listings.
