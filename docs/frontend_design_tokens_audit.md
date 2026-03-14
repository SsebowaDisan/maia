# Frontend Design Token Audit (Phase 0)

## Existing Global Token Sources
- `frontend/user_interface/src/styles/theme.css`
  - color primitives: `--background`, `--foreground`, `--card`, `--primary`, `--secondary`, `--muted`, `--accent`, `--destructive`
  - component colors: `--sidebar-*`, `--citation-*`
  - typography base: `--font-system-apple`, `--font-size`, `--font-weight-*`
  - radius base: `--radius` (+ derived `--radius-sm/md/lg/xl`)
  - chart colors: `--chart-1` to `--chart-5`
- `frontend/user_interface/src/styles/theme/assistant_answer.css`
  - message-surface and rich-text typography styles (class-based)

## Phase 0 Additions
- `frontend/user_interface/src/styles/tokens.css` imported by `index.css`
  - spacing scale (`--space-0`..`--space-12`) using a 4px grid
  - surface radius/shadow/border helper tokens
  - title/body type size helper tokens

## Guardrail For Next Phases
1. New pages/components in Agent OS phases should use existing CSS variables or the new spacing/surface/text tokens.
2. Avoid one-off pixel literals when an equivalent token exists.
3. Add to token files before introducing repeated values in feature components.

