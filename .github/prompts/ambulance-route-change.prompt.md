---
name: "Ambulance Route Change"
description: "Plan, implement, and verify a requested feature or fix in the Emergency Ambulance Route Selector. Use for changes to its Flask API, routing engine, interactive map, or standalone demo."
argument-hint: "Describe the feature, bug, or improvement to implement"
agent: "agent"
---

Implement the following requested change in the Emergency Ambulance Route Selector:

**Request:** ${input:task:Describe the feature, bug, or improvement}

Work through these steps in order. Do the implementation; do not stop after providing a plan.

1. **Establish the project context**
   - Read `README.md` and inspect the relevant code before editing.
   - Trace the requested behavior through every affected layer. The main surfaces are `engine.py`, `app.py`, `templates/index.html`, `city_data.json`, `tests/`, and `build_standalone.py`.
   - Treat `templates/index.html` as the source for the browser UI and embedded JavaScript engine. `build_standalone.py` generates `dist/ambulance_route_selector.html`; do not hand-edit generated output.
   - Check existing patterns, user changes, and the current behavior. Preserve unrelated work.

2. **Define the change**
   - Restate the request as a concise observable outcome and identify affected files and compatibility constraints.
   - Identify edge cases and the smallest relevant tests before making edits.
   - If a consequential product or behavior decision cannot be determined from the request or project conventions, ask one focused question before implementing. Otherwise, state reasonable assumptions briefly and proceed.

3. **Implement coherently**
   - Make the smallest complete change that achieves the requested outcome; follow existing naming, architecture, styling, and accessibility patterns.
   - Keep Python and JavaScript routing behavior aligned whenever the engine or route results change.
   - Preserve working behavior, API response shapes, and both server-backed and standalone usage unless the request explicitly requires a change.
   - Add or update focused tests for normal behavior, relevant edge cases, and invalid input where applicable.
   - Update `README.md` when setup, usage, or user-visible behavior changes.

4. **Verify the actual requirement**
   - Run the smallest relevant tests first. The project test suite is `python -m pytest -q`.
   - If the embedded JavaScript engine or its results changed, run `python tests/parity.py` when Node.js is available; report clearly if it is not.
   - If `templates/index.html` changed, run `python build_standalone.py` so the generated demo matches the source. Do not run commands that overwrite or discard unrelated user work.
   - For UI changes, inspect the resulting markup and interaction paths for responsive layout, keyboard operation, accessible labels/status, and browser-console errors where a browser is available.
   - Fix regressions caused by the change and rerun the relevant checks. Never claim a check passed unless it was actually run.

5. **Report the result**
   - Summarize the implemented behavior and key design decisions.
   - List the changed files using workspace links.
   - Give each validation command and its actual result; call out checks that could not run and why.
   - Mention remaining limitations only when there are any.
