# Supervisor-feedback execution runbook

Date: 2026-08-14

This runbook executes only the evidence that cannot be completed on the local
checkout. It obeys the project rule that code reaches the server only through
Git: no local file is copied or pushed directly to the server, and Codex does
not poll the server. The user starts and monitors each command and reports when
the result package is ready.

## 0. Bind the server checkout

After the approved commit has been pushed, open the existing server checkout
and fast-forward it. Replace the placeholders rather than using a wildcard to
select a repository.

```bash
source /etc/network_turbo

cd /root/autodl-tmp/<YOUR_CURRENT_REPOSITORY_DIRECTORY>
git pull --ff-only

export COLLECTION_REPO="$PWD"
export EXPECTED_COMMIT="<APPROVED_COMMIT_SHA>"
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python

test "$(git rev-parse HEAD)" = "$EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=no)"
```

Do not start either evidence stage if either `test` fails.

## 1. Close comments 1 and 2 from the immutable R3 archive

This is an offline job. It does not need or start CARLA and does not alter the
R3 archive. It verifies the known snapshot SHA-256, extracts it safely, then
produces the 80-rollout behaviour audit and the full solver/fallback taxonomy.

```bash
export R3_RESULTS_ROOT=/root/autodl-tmp/results/give_way_transformer/distinction_v1/r3_corrected_formal_v3
export R3_ARCHIVE="$R3_RESULTS_ROOT/r3_corrected_formal_snapshot.tar.gz"
export SF_RESULTS_ROOT="$R3_RESULTS_ROOT/supervisor_feedback_v1/r3_offline_v1"

mkdir -p "$SF_RESULTS_ROOT"

nohup env \
  PYTHON_BIN="$PYTHON_BIN" \
  R3_RESULTS_ROOT="$R3_RESULTS_ROOT" \
  R3_ARCHIVE="$R3_ARCHIVE" \
  SF_RESULTS_ROOT="$SF_RESULTS_ROOT" \
  bash "$COLLECTION_REPO/core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh" \
  > "$SF_RESULTS_ROOT/offline_launcher.log" 2>&1 &

echo $! | tee "$SF_RESULTS_ROOT/offline_runner.pid"
```

Read-only observation commands:

```bash
tail -F "$SF_RESULTS_ROOT/offline_launcher.log"
```

```bash
test -f "$SF_RESULTS_ROOT/SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json" \
  && cat "$SF_RESULTS_ROOT/SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json"
```

The final marker status must begin with `pass` (missing mechanism events remain
reported outcomes rather than a rerun trigger), the behaviour receipt must
account for 80 rollouts, and the cost receipt must say
`raw_taxonomy_status=pass` and
`deadline_evaluation_status=evaluated`, with
`raw_step_classification_status=pass`,
`raw_step_identity_status=pass`,
`corrected_attempted_latency_status=pass` and
`corrected_attempted_acceptance_status=pass`, plus
`failure_downstream_outcome_join_status=pass`. Final finite solver timing and
controller-acceptance accounting use factual solve attempts only;
`rule_bypass_no_solve` is counted separately, raw return statuses are retained,
every fallback/nonaccepted event joins exactly one canonical rollout outcome
(while a rollout may contain multiple events), and no logger flag is interpreted
as a mathematical feasibility certificate. The
transport package and hash receipt
are written beside `r3_offline_v1`:

```text
/root/autodl-tmp/results/give_way_transformer/distinction_v1/r3_corrected_formal_v3/supervisor_feedback_v1/supervisor_feedback_r3_offline_results.tar.gz
/root/autodl-tmp/results/give_way_transformer/distinction_v1/r3_corrected_formal_v3/supervisor_feedback_v1/supervisor_feedback_r3_offline_results.tar.gz.json
```

If the process is interrupted, rerun the identical `nohup` block. The archive
hash and extraction marker prevent evidence drift.

## 2. Start the externally managed Town05 CARLA instance

SF4 never starts or switches CARLA. Use the server's working launcher in a
separate terminal and keep that process alive:

```bash
cd /root/autodl-tmp
./start_carla_3d.sh
```

In the experiment terminal, bind the Python API and explicitly load Town05 if
the launcher defaulted to another map:

```bash
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHONPATH="$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:${PYTHONPATH:-}"

"$PYTHON_BIN" - <<'PY'
import carla

client = carla.Client("127.0.0.1", 2000)
client.set_timeout(30)
world = client.get_world()
if not world.get_map().name.endswith("Town05"):
    world = client.load_world("Town05")
print(world.get_map().name)
assert world.get_map().name.endswith("Town05")
PY
```

Town05 is required because the prediction data, route geometry, R3 controls
and all four dissertation claims are frozen to that map. Town10 results would
not be exchangeable with the existing evidence.

## 3. Run the SF4 preflight without a treatment rollout

SF4 toggles the complete application authority of the corrected
`reduced_intervention` rule-aware supervisor, not the historical `full`
configuration and not only the
last action filter. Both arms share the identically configured candidate logic.
Authority-on may apply reference, linearisation, heading-cost,
rule-SMPC-bypass, post-action, release/recovery and control-history channels;
authority-off logs them in shadow, never skips the solve and keeps non-risk
solver/control/state paths neutral. Zero requested activity is a scientific
result and must not trigger replacement runs.

```bash
export SF4_RESULTS=/root/autodl-tmp/results/give_way_transformer/distinction_v1/sf4_supervisor_behavioural_authority_v1
mkdir -p "$SF4_RESULTS"

env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  SF4_RESULTS="$SF4_RESULTS" \
  bash "$COLLECTION_REPO/core/scripts/carla/run_sf4_supervisor_behavioural_authority_ablation.sh" \
  --preflight-only
```

Proceed only if `SF4_PREFLIGHT_COMPLETE.json` reports `status=pass` and
`formal_rollouts_launched=0`.

The committed init106--115 JSON files are the frozen candidate authority.
Preflight independently reproduces their declared PCG64 continuation, accepts
only sub-`1e-12` numeric differences caused by historical NumPy uniform
conversion/float formatting, verifies canonical JSON and manifest SHA-256
binding, and never rewrites an existing frozen candidate. Material numeric,
schema, serialization or hash drift still fails closed before any rollout.

## 4. Run the excluded full-stack smoke gate

Before any formal receipt exists, execute the complete fixed-init105/assertive
risk-by-authority smoke factorial: fixed-on, fixed-off, adaptive-on and
adaptive-off. This fourth case is important because it exercises adaptive-risk
allocation and applied behavioural authority together before formal evidence
collection:

```bash
env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  SF4_RESULTS="$SF4_RESULTS" \
  bash "$COLLECTION_REPO/core/scripts/carla/run_sf4_supervisor_behavioural_authority_ablation.sh" \
  --smoke-only
```

Proceed only if `SF4_SMOKE_COMPLETE.json` reports `status=pass`,
`formal_rollouts_observed=0`, and four passing records with the exact four
factorial labels. Init105 and `_smoke/`
are explicitly excluded from the 80-rollout analysis and raw evidence. Smoke
results may be used only to repair runtime/integrity/manipulation defects, never
to tune for scientific direction.

## 5. Run or resume the 80-rollout SF4 matrix

```bash
nohup env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  SF4_RESULTS="$SF4_RESULTS" \
  bash "$COLLECTION_REPO/core/scripts/carla/run_sf4_supervisor_behavioural_authority_ablation.sh" \
  > "$SF4_RESULTS/sf4_launcher.log" 2>&1 &

echo $! | tee "$SF4_RESULTS/sf4_runner.pid"
```

Read-only progress and log commands:

```bash
env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  SF4_RESULTS="$SF4_RESULTS" \
  bash "$COLLECTION_REPO/core/scripts/carla/run_sf4_supervisor_behavioural_authority_ablation.sh" \
  --list-pending
```

```bash
tail -F "$SF4_RESULTS/sf4_runner.log"
```

If the server or CARLA stops, restart CARLA with Section 2, verify Town05, and
rerun the identical `nohup` block. Accepted receipts are re-hashed and skipped;
only predefined infrastructure failures may consume a new attempt. Collision,
yield failure, fallback/nonaccepted solving, non-completion and an unfavourable effect
direction are retained as scientific results.

### Infrastructure-cap exhaustion recovery

Do not delete attempts or merely raise `SF4_MAX_ATTEMPTS` if a key exhausts
all ten attempts. The dedicated recovery runner is admissible only when its
fail-closed audit finds exactly one exhausted pending key, every prior attempt
is classified as retryable CARLA infrastructure failure, every attempt includes
`carla_timeout`, and no valid or partial scientific measurement payload exists.
A `ran_successfully=false` summary written before the first simulation tick is
retained and hash-inventoried as failure provenance; it is not counted as a
scientific rollout. The audit recomputes the canonical complete-scenario
validator and cross-checks its result against every attempt record. It freezes
an immutable amendment inside that key's attempt tree,
revalidates all original contract execution-source hashes, preserves the
contract Git identity in subsequent raw configs, extends the cap to twenty for
that key alone, leaves every other key at ten, and retains all prior failures.
The amendment is included in both compact and full-raw evidence packages.

First run the complete recovery audit in the foreground. This creates and
idempotently revalidates the frozen amendment, but launches no rollout:

```bash
env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  SF4_RESULTS="$SF4_RESULTS" \
  bash "$COLLECTION_REPO/core/scripts/carla/run_sf4_infrastructure_recovery.sh" \
  --prepare-only
```

Proceed only after it prints `SF4 infrastructure recovery prepare-only: PASS`.
Then launch the identical audited runner without `--prepare-only`:

```bash
nohup env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  SF4_RESULTS="$SF4_RESULTS" \
  bash "$COLLECTION_REPO/core/scripts/carla/run_sf4_infrastructure_recovery.sh" \
  > "$SF4_RESULTS/sf4_recovery_launcher.log" 2>&1 &

echo $! | tee "$SF4_RESULTS/sf4_recovery_runner.pid"
```

This is an administrative missing-observation recovery, not a change to the
scientific stopping rule. Any valid scenario, non-empty trajectory/prediction/
controller measurement payload, non-infrastructure failure, source drift,
multiple exhausted keys or existing completion marker blocks the recovery.

## 6. Completion artifacts

The run is complete only when all of the following pass:

```bash
cat "$SF4_RESULTS/SF4_COMPLETE.json"
cat "$SF4_RESULTS/analysis/SF4_ANALYSIS_COMPLETE.json"
cat "$SF4_RESULTS/SF4_FULL_RAW_SNAPSHOT_COMPLETE.json"
```

Expected transport assets are:

```text
$SF4_RESULTS/sf4_supervisor_behavioural_authority_compact_evidence.tar.gz
$SF4_RESULTS/sf4_supervisor_behavioural_authority_compact_evidence.tar.gz.json
$SF4_RESULTS/sf4_supervisor_behavioural_authority_compact_evidence.tar.gz.files.json
$SF4_RESULTS/sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz
$SF4_RESULTS/sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.json
$SF4_RESULTS/sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.files.json
```

After the user reports completion, Codex will retrieve the two result packages,
verify their hashes locally, integrate SF1/SF2/SF4 tables and figures, rebuild
M1/W1/Q1, and then prepare the four-row response memo for both supervisors.
