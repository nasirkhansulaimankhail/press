# Local Helpdesk extraction integration

This branch is based on `univentures/current`, preserving the deployed Press source. It does not merge a newer upstream Press or Agent version.

The Helpdesk option implementation now lives in the paired local Frappe app `apps/univentures_press_custom`, branch `integration/helpdesk-extraction`. This Press branch keeps four non-guest whitelisted compatibility routes in `press/api/helpdesk_options.py`. They delegate to the byte-identical extracted implementation. No team/child-team or server-selection logic is duplicated in these wrappers.

Install the custom app on an isolated staging bench before enabling this Press branch's routes. The app requires Press and Helpdesk; its lifecycle hooks preserve existing ticket fields/template properties and move known Default template bindings to the new endpoints. Do not deploy the compatibility shim by itself. Both old and new route names require Frappe's authenticated whitelist dispatch.

The existing local Support URL `/helpdesk/my-tickets/new` is unchanged. No frontend bundle or Agent changes are part of this extraction.

See the custom app README for tests, staging acceptance and rollback. No production install, migrate, build, service restart or deployment has been performed. Preservation branches remain historical source records.
