# Git Workflow

Long-lived branches:
- `main` stable/production
- `develop` integration

Feature:
`feature/<owner>/<module>-<name>`

Examples:
- `feature/munees/projected-inventory`
- `feature/keerthi/plant-confirmation`
- `feature/yathish/requirement-engine`

Fix:
`fix/<owner>/<name>`

## Pull request must state
- owner/module
- change summary
- tables affected
- APIs affected
- screens affected
- migrations
- tests
- docs
- `TBD` items
- cross-team impact

## Merge gate
- update from `develop`
- tests pass
- one clean Alembic head
- contracts resolved
- no duplicate models
- no undocumented business-rule change

## Commit style
- `feat(requirements): add area coverage rule`
- `feat(inventory): add projected stock calculation`
- `fix(purchase): prevent pending PO double subtraction`
- `test(requirements): add box requirement cases`
- `docs(architecture): clarify central store`

Never casually change another teammate's table; agree schema first.
