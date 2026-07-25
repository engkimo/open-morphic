# Morphic Control Plane Strategy

Decision date: 2026-07-14
Last updated: 2026-07-20

## Product decision

Morphic will not try to beat Claude Code, Codex CLI, or Gemini CLI by cloning
their terminal UX and reimplementing every native harness feature. Morphic will
be the multi-engine control plane that preserves and coordinates those native
agent runtimes.

The winning category is:

> One terminal and canonical workspace harness for routing, supervising,
> comparing, handing off, and auditing work across Claude Code, Codex CLI,
> Gemini CLI, OpenHands, Ollama, and direct LLM gateways.

Native engines remain responsible for their strongest internal agent loops,
tools, subagents, skills, MCP integrations, and provider-specific behavior.
Morphic owns cross-engine session state, context projection, permission policy,
audit events, cost, normalized results, worktree isolation, evidence-based
selection, and handoff.

## Current-state finding

The Chat CLI foundation is strong and well tested, but it is still a technical
preview rather than a daily-driver coding agent:

- `morphic chat` and `morphic code` default to `LocalChatCouncilRuntime`, which
  returns deterministic planning text instead of running a coding agent.
- Chat hook and tool executors default to no-op.
- Route-backed council always invokes planner, critic, and leader sequentially,
  adding latency and cost even when one engine is enough.
- External CLI drivers are one-shot subprocess adapters. They do not yet expose
  streaming events, steering, approvals, resume, subagent state, or native
  harness activity through Morphic.
- Skills, MCP, hooks, memory, and context features exist in the wider product,
  but are not yet one coherent Chat CLI agent loop.

Validation on 2026-07-14: 3,478 unit tests passed and Ruff was clean.

## Implementation priorities

1. Connect `morphic code` to a single real routed engine without forcing a
   three-role council. Start behind explicit opt-in until permission propagation
   and failure behavior are verified.
2. Define a normalized engine event stream: engine start, assistant delta, tool
   request/result, approval, file change, verification, subagent activity, cost,
   wait state, and completion.
3. Upgrade Claude Code, Codex CLI, and Gemini CLI adapters from one-shot result
   capture to resumable, steerable native sessions while preserving their skills,
   MCP, hooks, and permission behavior.
4. Use adaptive orchestration: one engine for simple work, critic on risk or
   uncertainty, council only for complex or disputed work, worktrees for parallel
   writers, and cross-engine handoff after failure.
5. Build `.morphic` harness inspect/diff/export projections for AGENTS.md,
   CLAUDE.md, GEMINI.md, skills, hooks, MCP, and permissions. Never overwrite
   tool-specific files silently.
6. Prove the advantage with real repository benchmarks against Claude Code and
   Codex alone: completion rate, accepted patch rate, elapsed time, cost, human
   interventions, recovery rate, and context-handoff fidelity.

## First implementation slice

Add a route-backed direct runtime for Chat CLI that makes exactly one
`RouteToEngineUseCase` call, supports an explicit preferred engine, records the
engine result through existing chat events, and reports route failures rather
than silently presenting the deterministic local response as success.

Expose this first as an explicit CLI mode. Keep the current local deterministic
mode available as dry-run/fallback behavior until external-engine permission
mapping and live verification are complete.

## Phase 27 update

Codex CLI is the first permission-aware native direct adapter. The deprecated
`--full-auto` path was replaced with explicit `--sandbox` mapping and `--cd`
workspace scoping. Morphic `read-only`, `workspace-write`, and
`danger-full-access` map to the equivalent Codex sandbox. Morphic
`confirm-destructive` is deliberately rejected because `codex exec` is
non-interactive and cannot preserve an approval prompt channel.

Codex `--json` output is JSONL, not a single JSON object. Morphic now normalizes
thread, turn, tool, file change, plan, assistant, completion, failure, and error
records into provider-independent engine events while retaining the raw payload.
Until equivalent permission/workspace mappings exist for other native engines,
Chat CLI direct route explicitly requires `--engine codex_cli`.

## Phase 28 update

Normalized native events are now durable chat state rather than metadata visible only
on the final engine result. Direct-runtime turns carry `AgentEngineEvent` values, and
the send-message use case appends each one to the session ledger before the matching
council argument and assistant response. Raw Codex JSONL payloads remain attached for
audit and future parser evolution.

Workspace and permission controls now travel through `ScopedAgentEnginePort`, a narrow
capability separate from the common engine contract. Routing skips engines that do not
implement it instead of calling them with controls they might ignore. Codex is the first
scoped adapter. At the end of Phase 28, execution still buffered subprocess output until
completion; Phase 29 below closes that delivery gap.

## Phase 29 update

Codex direct execution now has a real incremental path. The subprocess runner drains
stdout and stderr concurrently; each JSONL stdout line is decoded with stateful thread
and sequence tracking and published before process completion. The application persists
the user message first, then appends native events immediately through its own ledger
sink. Buffered result metadata remains available for other callers without duplicating
streamed chat events.

Streaming is expressed as narrow capabilities (`StreamingScopedAgentEnginePort` and
`StreamingCouncilRuntimePort`), so adapters that cannot honor live delivery are never
mistaken for adapters that can. The next gaps are terminal live rendering and Codex
thread resume/steering; the durability pipeline itself is now in place.

## Phase 30 update

The line-oriented terminal now surfaces selected native events as concise progress after
their durable ledger append. Rendering is allowlisted to run, tool, file, plan,
completion, and error state. Raw provider payloads, generic progress/reasoning, unknown
events, and assistant-message content stay out of the progress channel. Details are
whitespace-normalized and capped, and presentation failure cannot cancel execution or
erase audit history.

The next control-plane primitive is native session continuity: resume the stored Codex
thread without losing Morphic workspace and permission guarantees, then expose steering
and cross-engine handoff on top of the same normalized ledger.

## Phase 31 update

Morphic now resumes an explicit Codex thread from its own append-only ledger. Native
session identity is stored with engine, original workspace root, and permission mode;
ledger replay reconstructs that binding after `morphic chat --resume`. The direct runtime
fails closed if current scope differs. Codex receives explicit sandbox/cwd options plus
`resume <thread_id> <prompt>`; Morphic never relies on Codex's ambiguous global `--last`.

Resume is a separate adapter capability rather than an assumption attached to all
streaming engines. The next gap is interactive steering/cancellation, followed by a
Claude Code adapter implementing the same scoped event and continuity contracts.

## Phase 32 update

Native process cancellation is now resource-safe. Both buffered and streaming subprocess
paths terminate the child when their asyncio task is cancelled, escalate to kill after a
two-second grace period, and re-raise the original cancellation. This closes the orphan
process risk before adding a user-facing `/cancel` or steering control channel.

## Phase 33 update

Claude Code is now a permission-aware scoped adapter. Morphic maps read-only to `plan`,
workspace-write to `acceptEdits`, and danger-full-access to an explicit bypass mode; it
rejects confirm-destructive in headless execution. The driver runs in the requested cwd.

More importantly for the control-plane strategy, Morphic no longer forces Claude to
user-only settings or a hard-coded tool allowlist. Claude's project/local settings,
CLAUDE.md discovery, skills, hooks, MCP, plugins, and native tool policy remain intact.
The next slice is `stream-json` normalization and explicit session resume; only after
that should Chat CLI direct mode allow `claude_code` alongside `codex_cli`.

## Phase 34 update

Claude Code now implements the same normalized streaming and provenance-checked resume
contracts as Codex. Morphic maps Claude system init, assistant text/tool use, user tool
results, and final results into the shared event vocabulary while retaining raw payloads.
Explicit Claude session ids are resumed only inside their original workspace and
permission scope.

Chat CLI direct mode now supports both `codex_cli` and `claude_code`. This is the first
working proof of the product thesis: two strong native harnesses keep their provider
features while Morphic owns a common durable ledger, progress view, safety boundary,
cost/result envelope, and session continuity. Next comes streaming input/steering and a
same-task comparative benchmark.

## Phase 35 update

Native resume identity is now provider-pinned end to end. A resume request carries its
owner engine as well as the session id; Morphic rejects preferred-engine mismatches and
skips every non-owner fallback before availability checks or process execution. Claude
session ids can never be offered to Codex, and Codex thread ids can never be offered to
Claude. This closes a subtle but critical cross-provider continuity failure introduced
when the second resumable native adapter came online.

## Phase 36 update

Streaming cancellation is now visible in Morphic's durable control plane, not only in
subprocess cleanup. The send-message use case appends a `turn_cancelled` event after the
user message and every native event received before interruption, then re-raises the
original cancellation. It does not manufacture a council decision or assistant success
for incomplete work.

Both terminal entry points now report Ctrl-C as `Cancelled.` with exit code 130. Together
with Phase 32 child-process termination, cancellation now has end-to-end semantics from
the user's terminal through the application ledger to the provider process. The next
step is an explicit steering/cancellation control channel that can stop a running turn
without exiting the Morphic process. Phase 36 passed all 3,523 unit tests with
repository-wide Ruff clean.

## Phase 37 update

Interactive chat now has an addressable active-turn controller. While a turn is running,
Ctrl-C is routed to the child turn task rather than the parent REPL. The existing
cancellation chain still terminates the provider process and appends `turn_cancelled`,
but the REPL reloads its `ChatSession` from the durable ledger and accepts the next
prompt. Replaying first is essential: it prevents the in-memory pre-turn sequence from
colliding with user, engine, and cancellation events already appended during the
interrupted turn.

The controller distinguishes its own cancellation request from cancellation of the
outer caller. An embedding application can still cancel the whole REPL with ordinary
asyncio semantics; only an explicit active-turn request becomes `TurnCancelledError`.
Repeated Ctrl-C requests do not interrupt cancellation cleanup. The controller also
restores the previous SIGINT handler when the turn ends, so idle Ctrl-C and one-shot
`morphic code` keep exit-code 130 behavior. User input and cancellation are durable for
non-streaming runtimes too, giving local council and native direct turns the same replay
contract. Phase 37 passed all 3,528 unit tests with repository-wide Ruff clean.

The next control-plane slice is an addressable local/remote command transport over this
controller, followed by provider-specific steering input where the native CLI supports
it. Cancellation semantics no longer need to be reinvented by each transport.

## Phase 38 update

The active-turn controller is now addressable from another local terminal through an
explicitly enabled, authenticated loopback transport. `morphic chat --control` creates a
random-port server only while a turn is active. A session-scoped descriptor under
`.morphic/control/` carries protocol version, loopback address, port, and a random token;
the directory is mode 0700 and the descriptor is mode 0600. The descriptor is removed
when the turn completes or cancellation cleanup finishes.

`morphic chat-control status` and `morphic chat-control cancel` provide the first
external control surface. The client refuses non-loopback descriptors, and the server
rejects invalid tokens, mismatched sessions, and unsupported commands before touching
the controller. The listener is opt-in and active-turn-only rather than a permanent
unauthenticated port. Remote use should initially go through an authenticated host
boundary such as SSH; direct network exposure remains deliberately unsupported.

This is Morphic's first reusable remote-control primitive above provider processes. The
next slice is authenticated `steer`: cancel the current turn, queue a bounded replacement
prompt, replay the ledger, and continue the same provider-bound native session. Phase 38
passed all 3,536 unit tests with repository-wide Ruff clean.

## Phase 39 update

The authenticated control transport now supports bounded `steer`. A steer request
accepts one non-empty replacement prompt of at most 2048 UTF-8 bytes. The first accepted
request queues the prompt and cancels the active child task; later requests during
cleanup cannot replace it. Invalid or oversized prompts are rejected before cancellation.

After provider cleanup appends `turn_cancelled`, the REPL replays the ledger, appends a
`turn_steered` audit event, and submits the replacement as a normal `user_message`. This
restores the provider session id with its original workspace and permission provenance,
so Codex or Claude continues through the existing explicit native resume contract.
Remote prompts beginning with `/` are always provider messages and never become local
REPL slash commands. The prompt body is stored once in the normal user event; the steer
event records only source and UTF-8 byte length.

This deliberately implements provider-neutral steering as cancel plus provenance-checked
resume, rather than depending on inconsistent provider stdin protocols. Phase 39 passed
all 3,542 unit tests with repository-wide Ruff clean. The next priority is a reproducible
same-task comparison harness for Codex alone, Claude alone, and Morphic-controlled runs,
with live paid execution remaining explicit opt-in.

## Phase 40 update

The first evidence harness is now offline and deterministic. One manifest pins the task,
workspace revision, verification checks, handoff assertions, and repetitions shared by
Codex CLI, Claude Code, and Morphic-controlled arms. A result set is accepted only when
every arm/trial cell appears exactly once and all passed assertions were declared before
the run.

Reports compare completion, accepted patch, verification, median elapsed time, cost,
human interventions, recovery, and context-handoff fidelity. Verification and handoff
scores are derived from named assertions. Morphic deliberately does not collapse these
dimensions into a subjective weighted winner score; it reports leaders per metric and
emits timestamp-free, sorted-key JSON for reproducible review.

`morphic benchmark agent-cli` only evaluates recorded JSON and cannot start Codex,
Claude, Morphic, or a paid API. The next slice should be a separate explicit opt-in
recorder with isolated worktrees, timeouts, cost caps, and captured verification evidence.
Phase 40 passed all 3,553 unit tests with repository-wide Ruff clean, and the built wheel
contains the benchmark package.

## Phase 41 update

The evidence harness now has a deliberately separate execution recorder. Its default
operation is a pure plan: validate manifest/config coverage, count trials, fingerprint
commands, and show the configured maximum estimate without creating a worktree or
starting an agent.

Live recording requires three explicit signals: execute, acknowledgement that commands
may be paid, and a cost cap covering the complete configured estimate. Every arm/trial
runs at the pinned revision in its own detached worktree outside the source repository.
Commands receive argv directly without a shell, have bounded timeouts, and worktrees are
released through `finally` cleanup.

Persisted evidence contains hashes and byte counts for argv/stdout/stderr plus exit,
timeout, elapsed, verification, and handoff outcomes. It never contains raw task prompts
or command output and never overwrites an existing evidence file. The authorized estimate
cap is audit data, not a claim that provider billing can be hard-stopped mid-request.
Actual provider cost, human interventions, recovery classification, and accepted-patch
review remain `pending_adjudication`; Morphic will not manufacture those values from
process success. The next slice is receipt parsing and deterministic adjudication into
the Phase 40 observation schema before any paid benchmark campaign.
Phase 41 passed all 3,566 unit tests with repository-wide Ruff clean. A real temporary
Git repository test verified pinned detached-worktree creation and removal, and the built
wheel contains both comparison and recorder modules. Exclusive evidence publication was
also verified to preserve an existing file under a competing write.

## Phase 42 update

Provider cost and human review now have an explicit evidence join instead of being
hand-entered directly into comparison observations. While raw agent stdout exists in
memory, the recorder attempts to normalize a privacy-safe receipt and then discards the
raw content. Codex usage is priced through the existing deterministic calculator using a
model or configured model hint; Claude retains its provider-reported total; Morphic uses
a strict `morphic_benchmark_receipt` envelope.

Receipts enforce provider-specific cost sources, non-negative usage, recalculated Codex
cost, and zero parse errors. A campaign becomes `normalized_receipts` only when every
trial parsed successfully. Missing data never silently becomes zero cost.

Independent review decisions bind accepted patch, human interventions, and recovery to
the exact agent argv SHA-256 and a review artifact SHA-256. The offline finalizer joins
those reviews with machine evidence, recomputes verification/handoff outcomes, enforces
the complete trial matrix and authorized actual-cost total, and rejects acceptance of a
failed provider/process run. It then emits the exact Phase 40 result schema with stable
JSON ordering and no timestamp.

No paid campaign was executed. The remaining pre-campaign gap is first-party Morphic
receipt emission and committed configuration/review templates, followed by a zero-cost
local rehearsal.
Phase 42 passed all 3,582 unit tests with repository-wide Ruff clean, and the built wheel
contains the comparison, recorder, receipt, and adjudication modules.

## Phase 43 update

Morphic now emits its own canonical benchmark receipt instead of requiring a wrapper to
manufacture one. `morphic code --benchmark-receipt` preserves the ordinary human output
and appends one sorted JSON envelope as the final stdout line. The envelope aggregates
non-negative token counters found in normalized completion events, sums council-turn
cost, and identifies the participating Morphic engine set. Raw provider payloads never
enter the receipt.

Failure and cancellation do not manufacture a zero-dollar receipt. Their final provider
cost may be unknown after an interrupted call, so receipt absence deliberately keeps the
campaign out of `normalized_receipts` until truthful evidence is available.

The benchmark pipeline also has a committed zero-cost rehearsal contract. Its three
arms are internal Python fixtures with a hard configured estimate and actual total of
$0. They exercise detached worktrees, every provider receipt parser, hashed evidence,
review fingerprints, and deterministic finalization without starting Codex, Claude,
Morphic routing, or an API. Rehearsal review decisions intentionally leave
`accepted_patch=false`; synthetic success is not represented as patch quality.

The real-repository rehearsal completed all three cells, published the five-file
manifest/config/evidence/reviews/results bundle exclusively, retained no raw command
output, and left no detached worktree behind. This closes the implementation gap before
a real campaign, but it is not competitive evidence. The next slice should add campaign
preflight and review-template authoring for a user-selected task/revision before any
paid execution is authorized.

Phase 43 passed all 3,591 unit tests with repository-wide Ruff clean. The built
wheel contains the rehearsal module and both committed JSON templates.

## Phase 43 publication checkpoint (2026-07-20)

Phase 43 was committed as `5678d43` (`Rehearse agent CLI receipts locally`) and
pushed to `agent/codex-direct-stream-resume`. Draft PR #44 recognized that commit as
its head, and lint, unit tests, UI build, Docker build, GitGuardian, and the draft review
gate all passed. The local source branch and origin are synchronized.

No paid benchmark campaign was executed. The next authorized development slice is
Phase 44: validate a user-selected manifest before execution, fingerprint required CLI
versions and commands, and generate an evidence-bound independent review template.
Campaign execution must remain a separate action requiring explicit paid acknowledgement
and a cost cap; preflight success alone never authorizes agent launch.

## Phase 44 update

Real campaigns now have a deterministic preflight artifact before execution. It requires
the manifest to contain the full resolved 40-character Git commit, validates exact
manifest/config coverage, normalizes operator-declared runtime versions, fingerprints
each version and every arm/check/handoff command, binds the complete manifest/config via
canonical SHA-256 without exposing the raw goal, and fixes
`execution_authorized=false`. Preflight resolves Git only; it never invokes a version
command, agent runtime, or paid API.

After recording, Morphic can generate a complete review template with null human
decisions for every expected arm/trial. The template binds the exact preflight and
normalized evidence SHA-256 plus each expanded agent argv SHA-256. A reviewer must fill
every decision, attach a review artifact fingerprint, and change
`review_completed` to true. Finalization validates the evidence binding automatically
and, when `--preflight` is supplied, validates the preflight binding too. Legacy Phase 42
reviews without these optional binding fields remain valid.

A real zero-cost rehearsal on commit `88326ae` generated a three-arm non-authorizing
preflight and a three-decision null review template. No external agent, version probe, or
paid API was started. Phase 44 closes campaign-authoring ambiguity; it does not authorize
the first paid comparison. The next slice should validate reviewer separation and add a
read-only campaign status command before any paid run is considered.

Phase 44 passed all 3,605 unit tests with repository-wide Ruff clean. The built
wheel contains the preflight module and runtime-version JSON template.

## Phase 45 update

Campaign review now has an explicit structural separation policy. A declaration names
the recorder/operator, the allowed reviewer IDs, and a minimum number of distinct
reviewers. Morphic normalizes and fingerprints that policy, binds it into pending and
completed review artifacts, rejects operator self-review, unauthorized IDs, insufficient
reviewer diversity, and policies impossible for the trial matrix. These IDs remain
operator declarations; the policy does not claim cryptographic identity authentication.

`morphic benchmark agent-cli-status` is a read-only lifecycle validator spanning
`manifest_ready`, `preflight_ready`, `recorded`, `review_pending`, `review_complete`, and
`finalized`. It validates artifact ordering, manifest/preflight contract hashes, evidence
estimate and matrix, review/preflight/evidence/policy bindings, reviewer separation, and
recomputed final results. Every stage reports `paid_execution_authorized=false`; status
inspection cannot launch or authorize a campaign.

A real zero-cost rehearsal at commit `d88f1f0` reached `review_pending` with a two-reviewer
policy. SHA-256 checks before and after status were identical for manifest, preflight,
evidence, review template, and policy files. No external agent, version probe, or paid API
was started. The next slice should add authenticated reviewer attestations or signed
artifact support without conflating declared IDs with verified human identity.

Phase 45 passed all 3,621 unit tests with repository-wide Ruff clean. The built wheel
contains the campaign status, reviewer policy, and policy template artifacts.

## Phase 46 update

Reviewer separation now has cryptographic provenance without moving private keys into
Morphic. A self-fingerprinted trust declaration binds the exact Phase 45 review policy to
reviewer IDs, globally unique key IDs, Ed25519 public keys, public-key fingerprints, and
active/revoked status. New trust declarations require at least one active key for every
allowed reviewer; retained revoked keys support explicit rotation history and fail closed
if used for a new signature.

`morphic benchmark agent-cli-attestation-template` produces one deterministic signing
request per distinct reviewer. Each statement binds the immutable task revision,
preflight and evidence hashes, policy and trust hashes, the completed reviews artifact,
and the canonical subset of decisions owned by that reviewer. The output contains the
exact base64 signing payload and no private-key material. Reviewers sign outside Morphic.

Trust-bound finalization and read-only status require a complete detached-signature bundle.
One valid active-key Ed25519 signature is required for every distinct reviewer. Unknown or
revoked keys, invalid signatures, missing reviewer coverage, modified statements, and
reviews/policy/trust mixing are rejected. Status exposes `review_attestation_pending`
until verification succeeds, while unsigned Phase 42-45 campaigns keep their existing
backward-compatible path. Every status remains non-authorizing for paid execution.

The important remaining boundary is key enrollment: a valid signature proves possession
of a key already placed in the trust declaration, but does not by itself prove real-world
identity or that the operator did not enroll a key they control. The next slice should
anchor reviewer keys in an organization CA or OIDC/Sigstore identity and sign the complete
campaign/result envelope, while retaining offline verification.

Phase 46 passed all 3,633 unit tests with repository-wide Ruff clean. The built wheel
contains the attestation module and reviewer trust template and directly declares
`cryptography>=46.0.5`. No external agent, private-key file, version probe, or paid API
was started.

## Phase 47 update

Reviewer key enrollment can now be anchored outside the recorder/operator. A normalized,
self-fingerprinted offline Ed25519 organization authority is bound into anchored reviewer
trust. `agent-cli-reviewer-enrollment-template` produces a canonical signing payload for
every retained reviewer key without exposing or reading the authority private key. Each
authority certificate binds the authority, benchmark, review policy, exact reviewer trust,
reviewer/key IDs, and reviewer public-key fingerprint. Missing, duplicate, mixed, or
invalid certificates fail closed, and anchored finalization requires the complete bundle.

The final campaign now has an optional authority-sealed boundary as well.
`agent-cli-campaign-envelope-template` binds manifest, preflight, evidence, completed
reviews, review policy, reviewer trust, authority enrollments, reviewer attestations,
results, and immutable campaign identity into one deterministic payload. It explicitly
fixes `paid_execution_authorized=false`. An authority-bound campaign remains at
`campaign_envelope_pending` until the external Ed25519 signature verifies; before key
enrollment it reports `reviewer_enrollment_pending`. Unanchored Phase 46 and unsigned
legacy campaigns retain their existing behavior.

This closes the operator-controlled key-enrollment gap when an organization distributes
the authority root independently. The remaining trust-distribution gap is explicit:
Morphic does not yet prove safe delivery of the root public key, certificate expiry,
authority revocation/rotation, or append-only transparency inclusion. The next slice
should add versioned root rotation and revocation plus a transparency proof, and only then
map the same contracts onto OIDC/Sigstore if online identity is desired.

Phase 47 passed all 3,646 unit tests with repository-wide Ruff clean. Real Ed25519
enrollment, reviewer attestation, and final campaign envelope signatures ran with
in-memory keys only. The built wheel contains the authority module plus authority and
anchored-trust templates. No external authority, agent, network identity provider,
private-key file, version probe, or paid API was started.

## Phase 48 update

The offline organization trust anchor now has a recoverable history instead of being one
permanent key. Every root after the genesis carries an exact rotation statement signed by
its predecessor. The active root signs a self-fingerprinted ledger containing the ordered
generation chain and revocations. Verification rejects gaps, reorderings, reused roots,
unknown revocations, invalid predecessor signatures, ledger tampering, and a revoked
active root.

New reviewer trusts can bind the active authority and the exact root-ledger SHA-256.
Finalization and the complete campaign envelope enforce that binding, while Phase 47
artifacts omit the new optional field from their fingerprints and signing bytes. This is
important for Morphic's control-plane strategy: governance artifacts remain portable and
offline-verifiable instead of depending on one hosted service or one agent vendor.

The campaign envelope can now be published into an append-only Merkle log. Leaves and
nodes use RFC 6962-style domain separation, the active root signs each tree head, and an
audit path proves inclusion of the exact campaign-envelope fingerprint. Ledger-bound
campaigns remain `transparency_pending` until that proof verifies. Complete old/new log
artifacts are accepted as append-only only when the old entries are an exact prefix.

Phase 48 passed 3,655 unit tests with repository-wide Ruff clean using in-memory Ed25519
keys only. No external authority, transparency server, identity provider, agent, or paid
API ran. Remaining boundaries are deliberate: genesis distribution and compromise reset
remain out-of-band, and complete-log prefix verification is not a compact consistency
proof or gossip protocol. The next trust slice should add compact consistency checkpoints
plus witnesses/gossip, or map the same verifier onto OIDC/Sigstore identities.

## Phase 49 update

Transparency growth can now be verified without exchanging complete historical logs.
Morphic implements the RFC 6962 `SUBPROOF` recursion and emits the unique minimal
consistency path between two active-root-signed tree heads. The verifier reconstructs
both advertised roots from the compact node list and rejects mismatched sizes, log IDs,
root ledgers, tree-head fingerprints or signatures, paths, and roots. The RFC seven-leaf
3-to-7 example shape and every prior size for trees through twelve leaves are covered.

An optional witness layer reduces reliance on one log authority. Witness trust binds a
log ID, globally unique Ed25519 keys, active/revoked state, and a strict-majority quorum.
The majority rule guarantees that any two accepted quorums intersect. Detached witness
signatures cover the exact old/new roots and sizes, both tree-head fingerprints, authority
root ledger, compact proof, and witness trust. Missing quorum, duplicate witnesses,
unknown or revoked keys, invalid signatures, and same-size different-root checkpoints
fail closed.

Campaign status preserves the Phase 48 inclusion-only path. When witness trust is
explicitly supplied, a campaign remains `witness_pending` until the compact proof and
witness checkpoint verify. Private-key-free consistency, witness-trust, and checkpoint
template CLI paths keep this governance portable across agent vendors and offline
environments.

Phase 49 passed 3,664 unit tests with repository-wide Ruff clean using in-memory keys
only. No external log, witness, identity provider, agent, or paid API ran. The remaining
boundary is operational exchange: Morphic verifies witness artifacts but does not yet run
a gossip network, attest real-world witness identity, or maintain a durable global
checkpoint registry. The next slice should add an append-only local checkpoint store and
authenticated peer exchange before considering an online witness service.

## Phase 50 update

Witnessed checkpoints now have a durable local trust boundary. Each registry record binds
its registry ID, contiguous sequence, previous-record SHA-256, authority-root ledger,
witness trust, compact consistency proof, and signed checkpoint into a deterministic
self-fingerprint. Replay revalidates the entire hash chain plus every authority, Merkle,
and witness signature. A partial tail, sequence gap, altered fingerprint or link, stale
extension, and same-size different-root split view all fail closed.

Append uses an exclusive file lock, `O_APPEND`, `fsync`, regular-file enforcement, and
mode 0600. Duplicate local appends and authenticated packet retries are idempotent, while
concurrent duplicate writers converge on one record. Read-only status does not create a
missing registry.

Peer exchange remains transport-neutral and private-key-free. A self-fingerprinted peer
trust artifact supports globally unique Ed25519 key IDs plus active/revoked rotation, with
at least one active key per declared peer. Detached signatures bind the source peer and
exact registry record, checkpoint, log root, and tree size. Import authenticates the peer
before entering the same locked append and conflict checks used for local storage.

Phase 50 passed 3,679 unit tests with repository-wide Ruff clean. Tests used in-memory
keys and local temporary files only; no external log, witness, peer service, agent, or paid
API ran. The remaining boundary is transport and catch-up: there is no listener, discovery,
real-world peer identity attestation, global consensus, or atomic multi-record range sync.
The next slice should add signed range bundles, atomic contiguous import, durable peer
cursors, and acknowledgements before exposing an online gossip transport.

## Phase 51 update

Offline peer catch-up now scales beyond one-record packets. A bounded contiguous range
statement binds the base hash, first/last sequence and record hashes, every record
fingerprint, registry, source peer, and peer trust to one Ed25519 signature. The receiver
authenticates that signature and validates every authority, witness, Merkle, record, and
range-chain binding before entering its write lock.

Inside the lock, existing overlap must match exactly and only the missing contiguous
suffix is appended. Gaps and forks cause no mutation. The suffix is encoded as one batch,
and process-level write errors truncate back to the original size before the lock is
released; crash-created partial tails remain detectable and fail closed on replay.

The receiver can sign an acknowledgement of the exact range and applied registry head.
The source persists verified acknowledgements in a separate mode-0600, locked,
hash-chained cursor ledger. Per source/receiver pair, cursor positions only advance;
exact retries are idempotent, while regression, same-sequence conflicts, invalid
signatures, and ledger tampering fail closed.

Phase 51 passed 3,686 unit tests with repository-wide Ruff clean. All signatures used
in-memory keys and all persistence used temporary local files; no agent, network peer,
listener, or paid API ran. The remaining trust boundary precedes transport: range and ack
artifacts bind one peer-trust snapshot, so historical cursor replay after trust rotation
requires retaining that old artifact. The next slice should add a signed peer-trust
generation ledger and rollover continuity before any online gossip listener.

## Phase 52 update

Peer identity continuity is now versioned instead of depending on one current trust file.
Generation one remains an out-of-band genesis. Every successor trust carries an exact
rotation statement approved by a strict majority of distinct active peers from the
immediately preceding trust. The statement binds registry, generation, predecessor and
successor fingerprints, and the automatically computed majority threshold.

Ledger replay verifies contiguous generations, stable registry identity, trust non-reuse,
certificate fingerprints, active predecessor keys, distinct peer identities, quorum, and
every Ed25519 signature. Minority approval, successor-only or revoked keys, invalid
signatures, gaps, reordering, reuse, and tampering fail closed.

The ledger resolves an acknowledgement's historical peer-trust fingerprint. Cursor
storage and replay can therefore verify pre-rotation acknowledgements under the old trust
and append post-rotation acknowledgements under the successor trust without splitting the
durable cursor chain. CLI paths remain private-key-free and accept exactly one trust
snapshot or generation ledger.

Phase 52 passed 3,691 unit tests with repository-wide Ruff clean. All rollover and
acknowledgement signatures used in-memory keys; no external peer, agent, listener, or paid
API ran. Remaining boundaries are genesis delivery, out-of-band pinning of the newest
ledger fingerprint, stale-ledger rollback detection, and transport. The next slice should
add an explicit opt-in loopback gossip transport with protocol versioning, nonce-based
challenge/replay defense, request limits, and deterministic shutdown before remote TLS.

## Phase 53 update

Checkpoint gossip now has a real but deliberately local network boundary. An operator must
explicitly start a short-lived server, which binds only to `127.0.0.1` on a random port. A
mode 0600 descriptor under an operator-selected path carries protocol version, registry,
source peer, a random instance id, and a 32-byte bearer token; its parent is mode 0700 and an
existing descriptor is never replaced.

Every connection begins with a one-use 32-byte client nonce and a fresh server nonce. Both
the challenge response and the request/response pair use HMAC-SHA256, binding protocol,
instance, registry, source peer, operation, and payload. Reused nonces, wrong tokens,
endpoint/version mismatch, over-limit messages, exhausted capacity, and timeouts fail
closed. Limits are fixed at 64 KiB requests, 2 MiB responses, eight concurrent clients,
1,024 retained nonces/requests, and two seconds per read or dispatch. Max requests, bounded
listener lifetime, cancellation, or context exit close the listener plus active client
writers/tasks and remove only the owned descriptor.

Transport authentication does not replace artifact trust. The server verifies every
pre-signed exact range before listening and never reads a private key. Fetch clients verify
the peer Ed25519 signature again using either a trust snapshot or the generation ledger;
full authority/witness/Merkle/registry verification still occurs in the existing atomic
range importer. Submitted acknowledgements are revalidated and pass through the durable
monotonic hash-chained cursor store. Invalid acknowledgement traffic cannot mutate it.

Phase 53 added explicit serve/status/fetch/ack CLI paths and passed 3,697 unit tests with
repository-wide Ruff and focused mypy clean. Tests used loopback sockets and in-memory test
keys only; no external peer, agent, paid API, or non-loopback listener ran. The remaining
boundary is a bounded resumable catch-up loop, durable transport audit, newest trust-ledger
rollback pinning, peer discovery, and remote mTLS. Phase 54 should build the pull/catch-up
loop and rollback pin before any remote bind.

## Phase 54 update

Checkpoint gossip now has a bounded resumable pull loop instead of requiring an operator to
manually repeat status, fetch, and import. It starts from the fully verified local registry
count, selects a pre-signed range containing that exact next sequence, independently checks
the range signature and status fingerprint, and then uses the existing authority, witness,
Merkle consistency, overlap, and atomic registry import path. A bundle may include an
already-present exact prefix; only its missing suffix counts against the record budget.

A separate mode 0600 JSONL sync audit holds a non-blocking exclusive process lock for the
entire loop. Records are deterministic, self-fingerprinted, hash-chained, fsynced, and bind
the exact loop-policy fingerprint. They capture imported range fingerprints, safe retry operation/attempt metadata, verified
registry-ahead recovery, trust advancement, and explicit stop reasons. Tokens, timestamps,
and raw exception text are never recorded. The registry remains the import source of truth:
if a crash occurs after registry fsync but before audit fsync, the last audited historical
head must still match the verified registry before a recovered record advances to its
current head.

Every audit record pins the accepted peer-trust generation, trust fingerprint, and ledger
fingerprint. A later run rejects a ledger older than any pin and rejects a fork at a pinned
generation before opening the descriptor. A correctly signed contiguous ledger extension
advances the pin. This is rollback protection against stale or forked remote input under the
preserved local files, not protection from a local attacker capable of rewriting the entire
registry and audit history.

Loop policy bounds rounds, newly imported records, attempts per request, and deterministic
backoff. Results stop with `up_to_date`, `range_gap`, `record_budget_exhausted`,
`round_budget_exhausted`, or `retry_exhausted`. The new gossip-sync CLI remains
private-key-free and passed 3,698 unit tests with repository-wide Ruff and focused mypy
clean. Only loopback sockets and in-memory test keys ran; no external peer, agent, paid API,
or non-loopback listener was used.

Phase 55 should add an explicit remote mTLS boundary: peer-id-bound certificate/SPKI
enrollment anchored to the existing Ed25519 peer trust, TLS 1.3 only, address allowlists,
hostname/IP verification, certificate rotation continuity, and no plaintext fallback.

## Phase 55 update

Checkpoint gossip now has an explicit remote-capable mutual TLS boundary. A deterministic
enrollment statement binds one non-CA leaf certificate's normalized DER and SPKI SHA-256
pins, subject and issuer, serial, validity interval, DNS/IP SANs, and dual client/server
authentication EKUs to one active Ed25519 peer identity signature. The signing template
and finalization CUI never read an identity private key.

Certificate rotation is a per-peer contiguous generation chain. Each successor binds the
exact predecessor enrollment fingerprint. TLS trust construction reverifies every identity
signature under the exact peer-trust fingerprint, rejects missing generations or registry
changes, and exposes only the highest generation as active. Active certificate and SPKI pins
must also be unique across peers. Runtime server and client credentials must match both
active pins, so an enrolled but superseded certificate cannot authenticate.

Transport protocol version two uses TLS 1.3 only and requires certificates on both sides.
The client verifies the CA chain, certificate hostname, explicit descriptor/server IP
allowlist, connected peer address, exact TLS-trust fingerprint, and server DER/SPKI pins.
The server verifies an explicit client IP allowlist, resolves the handshake leaf to exactly
one active peer, and requires the request's client peer ID to match. Its mode 0600 descriptor
contains no bearer token, and plaintext input never reaches the application protocol.

One-use nonce replay defense plus the existing 64 KiB request, 2 MiB response, concurrency,
timeout, retained-nonce, request-count, and deterministic cleanup bounds remain in force.
Private key files must deny group and other access. The CUI now covers enrollment template,
detached-signature finalization, trust publication, mTLS serve, and mTLS status; any loaded
TLS trust is cryptographically rechecked against its peer trust before network use.

Phase 55 passed 3,700 unit tests with repository-wide Ruff, focused mypy, and wheel build
clean. Tests used loopback sockets, temporary local CA/leaf certificates, and in-memory
Ed25519 identity keys only. No external peer, agent, paid API, or non-loopback listener ran.
Remaining operator boundaries are authentic CA/genesis distribution, DNS/address operations,
certificate revocation status and key custody. Phase 56 should wire fetch, acknowledgement, and resumable
sync CUI paths to protocol v2, then add revocation/expiry policy and authenticated discovery
without reintroducing bearer tokens or plaintext fallback.

## Phase 56 update

Checkpoint artifact operations no longer depend directly on the Phase 53 loopback transport.
Status, signed range fetch, and signed acknowledgement submission accept one typed authenticated
request sender, while an omitted sender preserves protocol v1 and every existing caller. The
reusable protocol-v2 client retains the exact mTLS descriptor, client peer identity, TLS trust,
leaf/key/CA paths, hostname, address allowlist, and timeout configuration.

This split deliberately leaves artifact trust outside transport trust. Every fetched range is
still verified under its exact peer-trust generation after receipt, and an acknowledgement
response must return the exact submitted signed artifact. The Phase 54 catch-up loop now uses
the sender for status and fetch only; whole-loop locking, hash-chained audit, registry-ahead
recovery, trust rollback/fork pins, retry delays, round/record budgets, and stop reasons remain
one implementation rather than an mTLS fork.

The CUI now exposes mTLS fetch, acknowledgement, and resumable sync. Before connecting, it
rebuilds TLS enrollment trust against the supplied peer-trust snapshot or the active generation
of a signed peer-trust ledger. Protocol v2 continues to require TLS 1.3, mutual certificates,
hostname and address checks, active DER/SPKI pins, one-use nonces, bounded messages, and a
token-free descriptor with no plaintext fallback.

Phase 56 passed 3,700 unit tests with repository-wide Ruff, focused mypy, and wheel build
clean. No external peer, paid API, or non-loopback listener ran. Phase 57 should add a
peer-signed explicit certificate revocation chain and deterministic expiry/pre-expiry policy
before authenticated discovery. TLS handshake expiry remains enforced, but Morphic does not yet
provide revocation status, warning windows, OCSP/CRL policy, or automatic enrollment/ack signing.

## Publication checkpoint (2026-07-15)

Phases 26-31 form the first complete native Codex control-plane vertical slice:
single-engine direct routing, explicit workspace/permission mapping, provider-neutral
events, incremental durable streaming, safe terminal progress, and provenance-checked
thread resume. The implementation passed 3,513 unit tests with repository-wide Ruff
clean before publication. The next development sequence is cancellation/steering first,
then a Claude Code adapter behind the same scoped streaming and resume capabilities.

## Phase 57 update

TLS trust now carries an explicit peer-signed revocation chain. Revocations bind registry,
peer, enrollment generation/fingerprint, peer-trust fingerprint, reason, and UTC timestamp;
only an active peer identity key may sign them, and revoked generations are excluded from
active certificate/SPKI resolution. Trust fingerprints include the normalized revocation set,
and re-verification checks both enrollment and revocation signatures.

Authenticated TLS server/client construction now applies a deterministic expiry policy before
opening transport: expired active leaves are rejected, while a configurable warning window is
reported as immutable `(peer_id, generation, expires_at, seconds_remaining)` tuples. Existing
callers retain defaults and TLS 1.3 handshake checks remain unchanged.

Phase 57 unit verification remains green at 3,700 tests; next work is to expose revocation
issuance/trust updates and expiry warnings through the CUI and add dedicated regression fixtures.

## Phase 58 update

The checkpoint TLS trust CLI now accepts an optional signed revocation bundle and publishes
the resulting revocation-aware trust fingerprint. This keeps revocation verification offline,
explicit, and compatible with the existing enrollment/trust artifact workflow. PR #44 CI is
green after the Phase 57 transport policy changes.

## Phase 59 update

Added private-key-free `CheckpointPeerTlsRevocationTemplate` generation and signed revocation
finalization. The template binds one enrolled peer/generation, reason, timestamp, trust hash,
and eligible active identity keys; finalization verifies the detached Ed25519 signature before
returning the self-fingerprinted revocation artifact.
## Phase 60 update

The revocation workflow is now exposed through two offline CUI commands: a private-key-free
template request and detached peer-signature finalization. Existing evidence is never
overwritten and finalized output remains deterministic JSON.
## Phase 61 update

TLS identity CLI regression now covers trust load, private-key-free revocation template,
detached peer signature finalization, and artifact round-trip validation.
## Completion checkpoint

The mTLS status CUI now exposes `tls_expiry_warnings` in JSON and the human summary, making
pre-expiry policy observable during actual operation. The current vertical slice is ready for
manual CLI smoke testing.
