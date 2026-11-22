# CLAUDE.md — Pishgarm Docs (دفتر اسناد پیشگرم)

You are building a small **Windows desktop app in Persian (RTL)** that lets a non-technical
company owner produce letters, pre-invoices (پیش‌فاکتور), invoices and statements
(صورت‌وضعیت) as ready Word files, file them by customer/project, and track a light task list.

Read these first, in order. They are the spec; follow them over your own assumptions.

1. `docs/01-overview.md` — goal, users, scope, non-goals
2. `docs/02-archive-analysis.md` — what 431 real documents taught us (source of every default)
3. `docs/03-data-model.md` — tables and fields
4. `docs/04-screens-and-flows.md` — screens, the issuing wizard, UX rules for the owner
5. `docs/05-documents-and-templates.md` — Word template contract (context schema), numbering, files
6. `docs/06-business-rules.md` — money math, clause rules, validation, statuses, auto-tasks
7. `docs/07-tech-stack-and-packaging.md` — stack, project layout, Windows installer
8. `docs/08-roadmap-and-acceptance.md` — phases and the acceptance tests that define "done"

## Non-negotiables

- **Stack:** Python 3.12, PySide6 (Qt 6), SQLite (SQLAlchemy 2.x), `docxtpl` for Word output,
  `jdatetime` for Jalali dates, `pypdf` for merging PDFs, `docx2pdf`/Word COM for PDF on Windows
  (LibreOffice fallback). Package with PyInstaller (one-folder) + Inno Setup. See doc 07.
- **The Word templates in `templates/` are the source of truth for layout.** They are the
  company's real documents turned into `docxtpl` templates. Do not redesign them; render them.
  The context each template expects is specified in doc 05 and exemplified in
  `templates/test_contexts/*.json`. Previews of correct output are in `templates/previews/`.
- **Seed data in `seed/*.json` must be loaded on first run** (issuers, accounts, parties,
  letter types, clauses, items, units, settings). Never hard-code these values in code.
- **Persian everywhere in the UI.** `QApplication.setLayoutDirection(Qt.RightToLeft)`,
  bundled Vazirmatn font for UI, Jalali dates only, thousands separators, money shown in
  Rial with live Persian words, input allowed in Toman or Rial (doc 06).
- **Money is integer Rial** in the database. Never store floats for money.
- **Never lose user data:** SQLite file + daily automatic backup (doc 07). Generated files are
  never overwritten silently; a re-issue creates a new version file.
- **The owner must never need Word to fix a number.** Everything that varies between documents
  is an input in the wizard; anything left free-text is a deliberate "متن آزاد" field.

## Working rules

- Build phase by phase (doc 08). After each phase, run the acceptance tests listed for it.
- Keep business logic (money, numbering, clause rules, context building) in pure-Python modules
  under `app/core/` with pytest unit tests. The UI layer only calls these.
- Template rendering test: for every template, render it with its `templates/test_contexts/*.json`
  using real `docxtpl` (add to pytest). `tools/render_test.py` is only a stand-in used while
  preparing this package; replace it with docxtpl in the app.
- When a requirement is ambiguous, check `docs/02-archive-analysis.md` and the files in
  `reference/samples/` before inventing behavior. Open questions are listed at the end of doc 08;
  do not silently decide them — leave a clearly named setting with the documented default.
- Development can happen on any OS, but the installer must be built on Windows
  (GitHub Actions `windows-latest` workflow is described in doc 07).

## Commands (create these as you scaffold)

- `python -m app` — run the app
- `pytest` — unit tests + template render tests
- `python tools/build_windows.py` — PyInstaller + Inno Setup (Windows only)
