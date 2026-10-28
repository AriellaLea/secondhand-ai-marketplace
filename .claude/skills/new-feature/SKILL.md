---
name: new-feature
description: Our way of building one feature of the second-hand marketplace (F1..F8 or a fix), from the docs to the commit. Use when the user asks to start, plan or implement a feature or a phase.
---

# New feature

Build one feature at a time, in this order. Do not skip a step.

## 1. Read
- `docs/PRD.md` (the feature's user story and acceptance criteria), `docs/Architecture.md`, `docs/tests.md`.
- `CLAUDE.md` (current status and decisions).
- The code the feature will touch.

## 2. Plan with the user
- Use the `grilling` skill: numbered questions, each with a recommended answer.
- Look up facts yourself; ask the user only for decisions.
- Sum up the decisions and wait for the user's OK before coding.

## 3. Write side (CQRS + Event Sourcing)
- A command in `app/commands/`: checks the role and the rules, appends one event with
  `append_event`, calls `project`, then commits once (event and read model together).
- A new event type in `app/events/types.py` and its projection in `app/events/projections.py`.
- Events are never updated or deleted.

## 4. Read side
- A query in `app/queries/`: reads the read model, filters by the viewer's role, writes nothing.

## 5. MVC
- Controller in `app/controllers/`: routes only (role check, call a handler, pick a view).
  No SQL, no business rule.
- View in `app/views/`: Hebrew, right to left, extends `base.html`.

## 6. Tests
- `tests/test_<feature>.py` named after the test ids of `docs/tests.md` (T-F8-1…).
- Cover the acceptance criteria, the refused cases (wrong role, wrong status, invalid input:
  nothing saved), and the replay of the events.
- Break a rule on purpose once to check that a test fails, then restore it.
- Run the whole suite: `.venv/bin/python -m pytest -q`.

## 7. Docs
- Update the PRD, `docs/Architecture.md`, `docs/tests.md` (new test ids) and the status
  and decisions in `CLAUDE.md`.

## 8. Manual check and commit
- Give the user the exact steps to try the feature in the browser.
- Show what changed; commit and push only after the user's OK. Never commit `.env.local`.
