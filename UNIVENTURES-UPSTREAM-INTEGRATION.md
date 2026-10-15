# Local upstream integration candidate

This branch merges Press6fb1a921221367fb2158e01bd22c700d453deee6 onto the preserved UniVentures source and the tested local Helpdesk/dependency integration. Production is unchanged. This is a local rehearsal candidate, not a deployment approval. The paired Agent target is0d1568b6c1796d190d37b925029958983e94047a with separate host-specific integration branches.

## Preserved behavior and adaptations

- Custom-app Helpdesk API plus legacy wrappers and exact Website User allow-list retained. Local Support route, team/shared domains, private regions, optional Stripe policy, analytics handling, timezone, DNS, Code Server and existing infrastructure-specific source changes are retained or adapted.
- New native builds prepare context on Agent. The Dockerfile retains the local cached-app helper; all Agent integration variants copy it. Code Server enablement propagates in build instructions. Preparing/Running progress and terminal events publish after commit. The old Press-side context preparation methods are retired in favor of the upstream pipeline; f2/f3 Agent variants separately retain the uploaded-context implementation for transition testing. Real v15/v16 builds, private apps, registry push/pull and deploy are still required.
- Backup payloads carry nested auth endpoint/provider/region and the legacy outer endpoint. Agent ordinary uploads accept both, preferring the nested endpoint. Configured/default bucket lookup retained. Streaming is disabled for custom endpoints and non-AWS providers until separately validated.
- All custom TLS payload/completeness reads use get_private_key(). The upstream encrypted-key migration is exercised against restored local data without printing keys.
- The upstream Site Plan catalog import/export and provider rewrite are excluded. All seven local plans, their allowed apps and provider eligibility are preserved; a fresh installation needs its own reviewed catalog. Initial rehearsal showed that excluding only Pro/Trial still imported684 other plans, including131 enabled offers. That behavior is not retained.
- External Python3.10 Ansible bridge retained; each play gets upstream's cloud_provider variable. No in-process global Ansible monkey patches are used. Per-host immutable Agent refs can be supplied through site_config.press_agent_release_refs; press_agent_repository_owner selects the fork. A configured per-host ref marks committed customizations so install/update roles skip historical S3/Code Server patch reapplication. Unmapped legacy hosts keep their original behavior. Agent commits remain local until explicitly published; do not run update/provision plays from this candidate.
- Prometheus rule saves during schema migration do not push remote monitor configuration. A deliberate monitor-rule refresh after the reviewed rollout is required. The first guarded rehearsal exposed and blocked the upstream network side effect; the corrected migration was retested from a fresh baseline restore.
- New MCP runtime is an optional, exact-commit dependency. Its Pydantic2.11 constraint conflicts with Framework16.23's2.12 profile. Without that extra, the handler rejects requests even if the saved flag is enabled; MCP functionality is not certified. Tests verify both disabled and enabled-without-runtime rejection. No setting is silently repaired in production.
- Version-upgrade API helpers are imported lazily from the upstream module to avoid a circular import; missing ValueWrapper import corrected. These runtime-name issues were found in the selected target during integration.

The Python profile remains3.14/Framework16.23 with reconciled SDKs and isolated Semgrep/Ansible tooling. HCloud is updated to the target's2.26 SDK. Existing production Framework is16.18.2, so this is not a byte-identical production-runtime rehearsal. Historical adjacent source backups are removed only from integration trees; preservation refs are unchanged. Agent's host-specific container/security/template changes are not enabled across unrelated hosts.

## Local build and tests

The protected bench is /Users/nasir/Projects/Frappe/V16/press-upstream-bench. It has its own DB and Redis, no workers/scheduler/web, an OS socket allow-list and Python guard. Use its README/wrapper. Keep private data, configs, keys and raw logs out of Git. Evidence is recorded in the Press workspace inventory/upstream-integration-20261015.

For a worktree outside the usual bench/apps layout, PRESS_BUILD_SOCKET_CONFIG may point at a minimal public JSON containing only socketio_port. This substitutes the dashboard's relative common-config import. Never point it at secret configuration. Build telemetry is disabled. Assets were built locally with this public-only input.

Source/mocked protocol checks are not disposable-host integration tests. Production release remains HOLD for tenant recovery, complete Agent/runtime/edge backups, MinIO full restore, real builds/deploys, Code Server sessions, TLS renewal/edge delivery, monitoring refresh, cloud provisioning and explicit production approval. No Git push, PR, host update or production restart is part of this branch.

## Role migration review gate

The selected upstream target consolidates legacy Press Admin/Press Member into Press User and fills missing Team Member roles with Developer. In this restored copy it removes25 old user-role assignments and adds20 Press User assignments. This upstream migration is retained, not silently undone. Helpdesk scoping and owner/member/unrelated OAuth/domain checks pass, but they do not establish full tenant resource/billing/admin permission parity. Broader role-guard acceptance is required before any rollout.
