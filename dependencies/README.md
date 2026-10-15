# Local Frappe 16 dependency profile

This branch targets the local Frappe 16.23 / Python 3.14 control plane. It retains the deployed Press base and Helpdesk extraction; it does not merge the proposed upstream Press upgrade. Keep this dependency work separate from the preservation and Helpdesk-only branches.

## Runtime boundaries

| Runtime | Declared requirements | Purpose |
| --- | --- | --- |
| Python 3.14 web/worker environment | Root `pyproject.toml` plus Framework/Helpdesk/Telephony/custom app manifests | Press application and controller imports; modern ansible-core remains here for existing ad-hoc controller imports |
| Python 3.10 playbook runner | `ansible-runner.txt` | Existing JSON bridge and legacy Ansible 3.4 playbook contracts; selected by `press_ansible_runner_python` |
| Python 3.11 audit tool | `semgrep.txt` | Semgrep 1.159; selected by Marketplace Settings `audit_bench_path`, whose `env/bin/semgrep` is invoked as a subprocess |

The external tools are installed and tested dependencies, not undeclared missing web packages. Do not install their requirements into the web environment. Modern ansible-core controller imports do not establish compatibility of remote ad-hoc console operations; those remain a separate workflow gate.

Shared web requirements agree with Framework: Requests 2.33, pyOpenSSL 26 and SQL Metadata 2.19. OCI, dnspython, Playwright, PostHog and pexpect use the versions tested in the local profile. Telephony uses Twilio 8.10.3, matching Press. Docker 7.1 fixes the Requests transport boundary; [Docker's release history](https://docker-py.readthedocs.io/en/stable/change-log.html) documents that compatibility change.

## Telegram integration

python-telegram-bot 22.5 uses asynchronous methods and bot initialization/shutdown; see its [Bot documentation](https://docs.python-telegram-bot.org/en/v22.5/telegram.bot.html). Press's synchronous `send`/`respond` API is preserved through a bounded bridge. It preserves parse modes, 4096-character truncation, chat/topic selection, failure logging and RetryAfter propagation. It also supports callers that already have an asyncio loop. SDK transport tests use in-memory Telegram responses; no messages are sent.

## Legacy Stripe compatibility artifact

Keep Stripe's current 2.56.0 API generation and request behavior. The distribution `stripe==2.56.0+univentures.1` replaces only vendored six with the official six 1.17.0 source, fixing its importer on Python 3.14. SDK runtime version and API-version/header selection remain unchanged. No active environment is patched manually.

Build the wheel from checksum-pinned official PyPI inputs:

```sh
python3 dependencies/build_stripe_compat.py /path/to/bench/staging/wheels
```

The script verifies input SHA256 values from `stripe-compat-sources.json`, writes deterministic wheel contents and RECORD hashes, and emits `stripe-compat-wheel.json`. Supply `--find-links /path/to/bench/staging/wheels` to the ordinary dependency resolver. This is a maintained compatibility artifact; the local version must not be silently replaced by an unrelated major Stripe SDK upgrade.

## Installation and verification

Create a new environment rather than modifying a working shared bench environment. Install all five app projects together with normal dependency resolution:

```sh
uv pip install --python /path/to/candidate/bin/python \
  --find-links /path/to/bench/staging/wheels \
  -e /path/to/bench/apps/frappe -e /path/to/bench/apps/press \
  -e /path/to/bench/apps/telephony -e /path/to/bench/apps/helpdesk \
  -e /path/to/bench/apps/univentures_press_custom
```

Install tool requirements in their declared Python versions, configure their existing selection paths on the isolated site, and run `python -m pip check` in all three environments. Keep resolved versions and app commits together. The staging locks include local paths and exact versions; they are not portable production deployment instructions or fully hashed locks for every platform.

`tests/test_runtime_contracts.py` exercises Telegram SDK lifecycle/serialization/error behavior, Stripe API requests/dictionary access/webhook signatures, Docker's local Unix-socket transport with Framework Requests, SQL/DNS parsing, disabled PostHog keyword APIs and Twilio serialization. No production service is contacted. `tests/check_tools.py <bench>` checks the real bridge's inspect/success/async/failure behavior on localhost and a real Semgrep scan with metrics/version checks disabled.

Successful dependency resolution and these local checks do not establish backup/build/deployment/billing/OAuth/Agent or remote provisioning compatibility. Those remain gates in the pre-upgrade checklist.
