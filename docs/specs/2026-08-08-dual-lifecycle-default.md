# Dual lifecycle as the default for new projects

## Claim

`sdlc-pilot` 0.21 makes the canonical dual lifecycle the default for an empty
target repository, while preserving exact 0.19.2 behavior for repositories that
explicitly select legacy. Existing SDLC artifacts never determine the route by
themselves: without a lifecycle profile they produce `migration-required` and
no lifecycle state is written.

## Decision

The project-level profile is the only persisted lifecycle selection:

```json
{
  "profile_format": "sdlc-lifecycle-profile-v1",
  "selection": "new-project-default-v1 | explicit-migration-v1",
  "mode": "dual-lifecycle-v1 | legacy-0.19.2"
}
```

It lives at `<target-repo>/.sdlc/lifecycle.json` and should be committed with
the project. The profile contains no mutable task state, credentials, approval
identity, contract contents, or evidence.

## Routing contract

| Target state | Router decision | Writes allowed |
| --- | --- | --- |
| No profile and no SDLC artifacts | `new-project-default` → persist dual profile → canonical product/delivery route | Only the new profile before canonical work |
| Profile selects `dual-lifecycle-v1` | canonical product/delivery route | Canonical ledger through its CAS API only |
| Profile selects `legacy-0.19.2` | pinned 0.19.2 runbook | Existing legacy protocol only |
| No profile and any legacy, preview, control, or dual-ledger artifact | `migration-required` | None |
| Explicit preview command | preview route | `.sdlc/preview/<run-id>/` only |

`/sdlc migrate --mode dual-lifecycle-v1` over an existing SDLC artifact needs
an explicit confirmation flag. Migration only records the user's selection: it
does not reinterpret `STATE.md`, legacy records, preview output, or a prior
dual ledger as another artifact type.

## Non-goals

- Do not globally rewrite existing project state.
- Do not manufacture `.sdlc-control/dual-lifecycle/authority.json`; its
  configured principal and approval policies remain a project-owner decision.
- Do not make preview outputs canonical or use them as legacy evidence.
- Do not make the local-serial ledger a multi-worktree transport.
- Do not coordinate a profile selection with a concurrent old-version or manual
  SDLC writer; profile selection is a local-serial repository operation.

## Acceptance checks

- A clean target resolves to dual and persists that decision before its first
  canonical operation.
- Every public SDLC entry that can write project state resolves the profile;
  `migration-required` permits no writes outside an explicit preview run.
- Legacy, preview, control, and dual-ledger artifacts each require an explicit
  profile selection when no profile exists.
- An invalid or symbolic-link profile fails closed.
- Selecting dual over existing artifacts requires an explicit confirmation and
  leaves those artifacts byte-for-byte unchanged.
- Full offline unit, static, legacy-runbook, and policy validation pass.
