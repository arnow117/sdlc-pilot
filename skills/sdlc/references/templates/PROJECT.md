<!--
Project context template.
Copy the body to <target-repo>/.sdlc-v1/project.md and replace every placeholder
with facts verified from the repository. Remove this comment after copying.
-->

# Project Context: <project-name>

## Purpose

<What this project does, who uses it, its main inputs and outputs.>

## Tech stack

| Area | Technology | Why / source |
|---|---|---|
| Runtime | <value> | <repository evidence> |
| Framework | <value> | <repository evidence> |
| Storage | <value or none> | <repository evidence> |
| External systems | <value or none> | <repository evidence> |

## Entry points

| Purpose | Path or command | Notes |
|---|---|---|
| Start | <path/command> | <notes> |
| Main flow | <path/symbol> | <notes> |
| Configuration | <path> | <notes> |

## Commands

```yaml
commands:
  unit: "<command or none>"
  coverage: "<command or none>"
  e2e: "<command or none>"
  typecheck: "<command or none>"
  lint: "<command or none>"
  build: "<command or none>"
```

## Surface map

Use repository-relative globs. Roles and modes must exist in `role-routing.md`.

```yaml
surfaces:
  - name: <surface-name>
    globs: ["<path/**>"]
    roles: [<role>]
    modes: [correctness]
```

## Conventions

- <Naming, module, testing and error-handling conventions verified in the repository.>
- <Important project instructions and prohibited actions.>

## Known risks

| Risk | Affected area | Current handling |
|---|---|---|
| <risk> | <path/surface> | <handling or gap> |

## Deployment

```yaml
target: <static-site | container | vps | other | none>
config_paths: [<paths>]
environments:
  dev: <meaning or none>
  staging: <meaning or none>
  canary: <meaning or none>
  full: <meaning or none>
health_check: <path/command or none>
```

Do not include secrets. Record where configuration comes from, not secret values.

## Repository context sources

```yaml
root_guidance: <AGENTS.md path or none>
scoped_guidance: [<applicable AGENTS.md paths>]
canonical_documents: [<long-lived architecture, goal, product, or development document paths>]
repo_context:
  status: <ready | stale | none>
  analyzed_commit: <commit or none>
```

List only source paths verified for the current repository state. This section is an index: do not copy
long-lived document prose into `project.md`, and do not treat `.sdlc-v1/` as repo-context input.

## AI readiness

<Short factual summary of project instructions, scoped commands, test discoverability,
type information, generated-file noise and remaining gaps.>
