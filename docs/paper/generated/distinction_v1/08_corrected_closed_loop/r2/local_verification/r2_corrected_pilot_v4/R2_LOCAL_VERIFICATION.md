# R2 corrected-pilot local verification

Status: **PASS**

- 10/10 corrected-v1 pilot rollouts passed; native collisions: 0.
- 1874 valid prediction/control steps were audited.
- Maximum per-rollout P95 solver time: 0.1038 s (gate: 0.5 s).
- Pulled archive SHA256: `e730200d8afb7e333ca708aaeebb5b832794ca420cbcb6d301d46271c167682c` (153 files).
- Runner log SHA256: `a05e9a9bf05ed46a4298dd86f7150f3b6665950c54d9bca974f17601fa5b5371`.
- One pre-restart launch failed from persistent CARLA spawn state; after a clean restart, all 10 accepted rollouts started on their first attempt.

Scientific boundary: this is a deployment/runtime gate, not an effect-estimation sample. The descriptive cell table must not be cited as evidence that B1 beats B0 or that adaptive risk beats a fixed policy.
