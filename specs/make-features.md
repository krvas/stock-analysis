I have a master backlog file (`feature-list.md`), an architectural reference (`STATE.md`), and a feature specification template (`feature-template.md`).

Your task is to take the requested feature(s) from `feature-list.md` and convert them into clean, standalone Markdown feature files inside `specs/features/`, strictly following the structure defined in `feature-template.md`.

---

### Context Files To Reference:
- `@feature-list.md` (Source of rough feature descriptions and notes)
- `@STATE.md` (System architecture, conventions, file paths, and current codebase state)
- `@feature-template.md` (The required structure and layout for individual feature specs)

---

### Instructions:

1. **Analysis & Enrichment:**
   - Map the rough requirements against `@STATE.md` to identify exact target file paths, relevant database tables, dependencies, and modules affected.
   - Expand vague notes into explicit, actionable **Acceptance Criteria** (formatted as a checklist).
   - Define clear **Out of Scope** boundaries to prevent scope creep during Cursor execution.
   - Include specific **Error Handling & Edge Cases** that Cursor must account for based on our codebase conventions in `@STATE.md`.

2. **Output Format:**
   - Generate the complete contents for each feature file using `@feature-template.md`.
   - Name the file using sequential numbering and kebab-case (e.g., `specs/features/01-duckdb-exporter.md`).
   - Output each spec inside a single labeled code block so I can easily copy or save it directly.

3. **Target Feature(s):**