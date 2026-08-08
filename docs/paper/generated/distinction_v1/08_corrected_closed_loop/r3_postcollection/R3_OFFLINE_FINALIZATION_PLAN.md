# R3 post-collection offline finalization plan

## Incident classification

The prespecified R3 v3 matrix completed all 80 unique treatment–initialisation keys. Seven failed infrastructure attempts remain in the attempt ledgers and all 80 scientific rollouts have passing immutable receipts. No treatment key is pending and no additional CARLA rollout is authorised.

The collection runner then stopped during derived metrics generation because the legacy `ClosedLoopTrajectory` loader forwarded the appended `actor_geometry` telemetry field into the dataclass constructor. This is a forward-compatibility failure after raw collection, not a simulation, prediction, control, treatment, outcome or raw-integrity failure.

## Permitted repair

The repair filters trajectory dictionaries to the declared dataclass init fields when constructing legacy metric objects. It does not rewrite the pickle or change any metric input field. A dedicated offline finalizer independently verifies:

1. 80 accepted receipts, zero pending keys and zero interrupted attempts;
2. every receipt against its immutable raw-evidence hash;
3. the original collection commit and every critical source against the frozen source manifest and original Git objects;
4. that the only critical-source drift is the declared loader compatibility change;
5. unchanged raw receipt hashes after derived post-processing;
6. all post-CARLA gates, matrix integrity checks, frozen analyses, study-stop gate and archive member hashes.

The final archive preserves both the collection and finalizer commits, the original source manifest, raw-collection completion marker, repair provenance, frozen repair sources, finalization report and logs. `R3_COMPLETE.json` is written only after archive readback succeeds.

## Scientific boundary

Scientific adverse outcomes remain valid evidence and cannot trigger new data collection. The repair is derived-only and cannot alter control actions, target behaviour, prediction outputs, raw trajectories, collision telemetry, completion events or treatment assignment. Once the offline integrity and study-stop gates pass, the CARLA experimental programme is closed.
