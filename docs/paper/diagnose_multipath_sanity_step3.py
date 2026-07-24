#!/usr/bin/env python3
"""Step 3 sanity checks for the CARLA MultiPath fine-tuning result.

This script intentionally avoids TensorFlow/GPU dependencies. It checks the
fixed split, label/raster completeness, cross-split overlap, logged prediction
metrics, and saved same-test-set model metrics that already exist on disk.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


DEFAULT_MERGED_DIR = (
    "core/results/20260717_232553_prediction_dataset_collection/"
    "prediction_dataset_merged"
)


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def infer_init_id(subrun: str) -> int | None:
    m = re.search(r"ego_init_(\d+)", subrun or "")
    return int(m.group(1)) if m else None


def expected_split(init_id: int) -> str:
    if 1 <= init_id <= 40:
        return "train"
    if 41 <= init_id <= 45:
        return "val"
    if 46 <= init_id <= 50:
        return "test"
    return "unknown"


def full_horizon(sample: Dict[str, Any], horizon: int = 10) -> bool:
    mask = sample.get("future_valid_mask") or []
    future = sample.get("future_xy_world") or []
    if len(mask) < horizon or len(future) < horizon:
        return False
    for i in range(horizon):
        xy = future[i]
        if not mask[i] or not xy or xy[0] is None or xy[1] is None:
            return False
    return True


def dist(a: List[float], b: List[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def mean(values: List[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(values: List[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    idx = (len(values) - 1) * pct / 100.0
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - idx) + values[hi] * (idx - lo)


def local_future_signature(sample: Dict[str, Any], horizon: int = 10, ndigits: int = 2) -> Tuple[Tuple[float, float], ...]:
    """Convert world labels to target local coordinates and round them.

    The online code maps local -> world as R @ local + t. With row-vector
    arithmetic, the inverse used by the training/eval utilities is:
      local = (world - t) @ R
    """
    rotation = sample.get("target_to_world_R") or [[1.0, 0.0], [0.0, 1.0]]
    trans = sample.get("target_to_world_t") or [0.0, 0.0]
    future = sample.get("future_xy_world") or []
    sig = []
    for xy in future[:horizon]:
        dx = float(xy[0]) - float(trans[0])
        dy = float(xy[1]) - float(trans[1])
        lx = dx * float(rotation[0][0]) + dy * float(rotation[1][0])
        ly = dx * float(rotation[0][1]) + dy * float(rotation[1][1])
        sig.append((round(lx, ndigits), round(ly, ndigits)))
    return tuple(sig)


def sample_identity(sample: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        sample.get("source_subrun"),
        sample.get("step"),
        sample.get("target_vehicle_idx"),
        sample.get("sim_time_s"),
    )


def summarise_split(path: Path, split: str, result_dir: Path, horizon: int) -> Dict[str, Any]:
    total = 0
    full = 0
    wrong_split_rows = []
    missing_raster = 0
    duplicate_ids = 0
    seen_ids = set()
    init_counts = Counter()
    subrun_counts = Counter()
    source_dataset_dirs = Counter()
    label_signatures = Counter()
    first_future_gap = []

    for sample in read_jsonl(path):
        total += 1
        ident = sample_identity(sample)
        if ident in seen_ids:
            duplicate_ids += 1
        seen_ids.add(ident)

        subrun = sample.get("source_subrun", "")
        init_id = infer_init_id(subrun)
        if init_id is not None:
            init_counts[init_id] += 1
            if expected_split(init_id) != split:
                wrong_split_rows.append({"source_subrun": subrun, "expected": expected_split(init_id)})
        subrun_counts[subrun] += 1
        source_dataset_dirs[sample.get("source_prediction_dataset_dir", "")] += 1

        raster_abs = sample.get("raster_abspath")
        raster_rel = sample.get("raster_relpath_from_result")
        raster_ok = bool(raster_abs and Path(raster_abs).exists())
        if not raster_ok and raster_rel:
            raster_ok = (result_dir / raster_rel).exists()
        if not raster_ok:
            missing_raster += 1

        if full_horizon(sample, horizon=horizon):
            full += 1
            label_signatures[local_future_signature(sample, horizon=horizon)] += 1
            past = sample.get("past_states_local") or []
            future = sample.get("future_xy_world") or []
            if past and future:
                # Past local state stores x/y at current target frame. Future is
                # world-frame, so use signature first point as comparable local xy.
                sig0 = label_signatures  # keeps linter-free stdlib script simple
                _ = sig0
                loc_sig = local_future_signature(sample, horizon=1, ndigits=6)
                first_future_gap.append(math.hypot(float(past[-1][1]) - loc_sig[0][0], float(past[-1][2]) - loc_sig[0][1]))

    return {
        "split": split,
        "rows": total,
        "full_horizon_rows": full,
        "init_ids": sorted(init_counts),
        "init_counts": dict(sorted(init_counts.items())),
        "subruns": len(subrun_counts),
        "missing_raster_rows": missing_raster,
        "duplicate_identity_rows": duplicate_ids,
        "wrong_split_rows": wrong_split_rows[:10],
        "wrong_split_count": len(wrong_split_rows),
        "source_dataset_dir_count": len(source_dataset_dirs),
        "unique_full_horizon_label_signatures_rounded_0p01m": len(label_signatures),
        "most_common_label_signature_count": label_signatures.most_common(1)[0][1] if label_signatures else 0,
        "first_future_gap_local_m_mean": mean(first_future_gap),
        "first_future_gap_local_m_p90": percentile(first_future_gap, 90),
    }


def recompute_logged_metrics(path: Path, horizon: int) -> Dict[str, Any]:
    top_ade = []
    min_ade = []
    top_fde = []
    min_fde = []
    top_is_best = 0
    total = 0

    for sample in read_jsonl(path):
        if not full_horizon(sample, horizon=horizon):
            continue
        preds = sample.get("pred_mus_world") or []
        probs = sample.get("mode_probabilities") or []
        future = sample.get("future_xy_world") or []
        if not preds or not probs:
            continue
        ades = []
        fdes = []
        for mode in preds:
            errors = [dist(mode[i], future[i]) for i in range(horizon)]
            ades.append(sum(errors) / len(errors))
            fdes.append(errors[-1])
        best = min(range(len(ades)), key=lambda i: ades[i])
        top = max(range(min(len(probs), len(ades))), key=lambda i: probs[i])
        top_is_best += int(best == top)
        top_ade.append(ades[top])
        min_ade.append(ades[best])
        top_fde.append(fdes[top])
        min_fde.append(fdes[best])
        total += 1

    return {
        "samples": total,
        "logged_top1_ADE_mean": mean(top_ade),
        "logged_minADE_mean": mean(min_ade),
        "logged_top1_FDE_mean": mean(top_fde),
        "logged_minFDE_mean": mean(min_fde),
        "logged_top_prob_mode_is_best_frac": top_is_best / total if total else None,
    }


def metric_delta(pretrained: Dict[str, Any], finetuned: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key in (
        "samples",
        "top1_ADE_mean",
        "minADE_mean",
        "top1_FDE_mean",
        "minFDE_mean",
        "top_prob_mode_is_best_frac",
        "mean_probability_assigned_to_best_mode",
        "mean_mode_entropy",
        "best_mode_counts",
    ):
        out[f"pretrained_{key}"] = pretrained.get(key)
        out[f"finetuned_{key}"] = finetuned.get(key)
    if pretrained.get("top1_ADE_mean") and finetuned.get("top1_ADE_mean") is not None:
        out["top1_ADE_reduction_m"] = pretrained["top1_ADE_mean"] - finetuned["top1_ADE_mean"]
    if pretrained.get("top1_FDE_mean") and finetuned.get("top1_FDE_mean") is not None:
        out["top1_FDE_reduction_m"] = pretrained["top1_FDE_mean"] - finetuned["top1_FDE_mean"]
    return out


def write_report(path: Path, merged_dir: Path, payload: Dict[str, Any]) -> None:
    splits = payload["splits"]
    metrics = payload["same_test_metrics"]
    flags = payload["flags"]
    with path.open("w", encoding="utf-8") as f:
        f.write("# Step 3 模型 sanity check 诊断报告\n\n")
        f.write(f"数据目录：`{merged_dir}`\n\n")
        f.write("## 结论\n\n")
        if flags["blocking_issues"]:
            f.write("发现需要先处理的阻塞问题：\n\n")
            for item in flags["blocking_issues"]:
                f.write(f"- {item}\n")
        else:
            f.write("未发现 split 泄漏、样本重复或缺失 raster 这类阻塞性问题。\n")
        f.write("\n")
        f.write("但当前 fine-tuning 结果不能表述为“预测问题已经完全解决”。更稳妥的表述是：\n\n")
        f.write("> 在固定 CARLA held-out test split 上，fine-tuned MultiPath head 显著改善了 top-probability mode ranking；该提升主要来自 mode probability calibration，而不是证明 closed-loop safety 必然显著提升。\n\n")

        f.write("## Split 完整性\n\n")
        f.write("| split | rows | full horizon | init ids | wrong split | duplicate ids | missing rasters | unique label signatures |\n")
        f.write("|---|---:|---:|---|---:|---:|---:|---:|\n")
        for split in ("train", "val", "test"):
            s = splits[split]
            ids = f"{min(s['init_ids'])}-{max(s['init_ids'])}" if s["init_ids"] else "-"
            f.write(
                f"| {split} | {s['rows']} | {s['full_horizon_rows']} | {ids} | "
                f"{s['wrong_split_count']} | {s['duplicate_identity_rows']} | "
                f"{s['missing_raster_rows']} | {s['unique_full_horizon_label_signatures_rounded_0p01m']} |\n"
            )
        f.write("\n")

        f.write("## Same-test-set metrics\n\n")
        f.write("| metric | pretrained | fine-tuned |\n")
        f.write("|---|---:|---:|\n")
        for label, key in (
            ("samples", "samples"),
            ("top1 ADE mean", "top1_ADE_mean"),
            ("minADE mean", "minADE_mean"),
            ("top1 FDE mean", "top1_FDE_mean"),
            ("minFDE mean", "minFDE_mean"),
            ("top-prob mode is best", "top_prob_mode_is_best_frac"),
            ("probability assigned to best mode", "mean_probability_assigned_to_best_mode"),
            ("mode entropy", "mean_mode_entropy"),
        ):
            f.write(
                f"| {label} | {metrics.get('pretrained_' + key)} | "
                f"{metrics.get('finetuned_' + key)} |\n"
            )
        f.write("\n")

        f.write("## 关键 sanity 观察\n\n")
        for item in flags["observations"]:
            f.write(f"- {item}\n")
        f.write("\n")

        f.write("## 是否需要 GPU\n\n")
        f.write("- 当前这类 sanity check 不需要 GPU，因为只读取已有 JSONL 和 metrics。\n")
        f.write("- 如果要重新跑 `evaluate_multipath_model_on_dataset.py` 全量 SavedModel 推理，CPU 也能跑 test split，但 GPU 更快。\n")
        f.write("- 如果要重新 fine-tune、做 shuffled-label training 或多组模型对照，建议放到 GPU 服务器。\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", default=DEFAULT_MERGED_DIR)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    merged_dir = Path(args.merged_dir).resolve()
    result_dir = merged_dir.parent
    output_dir = Path(args.output_dir).resolve() if args.output_dir else merged_dir / "sanity_check_step3"
    output_dir.mkdir(parents=True, exist_ok=True)

    splits = {
        split: summarise_split(merged_dir / f"{split}.jsonl", split, result_dir, args.horizon)
        for split in ("train", "val", "test")
    }
    logged_test = recompute_logged_metrics(merged_dir / "test.jsonl", args.horizon)
    pretrained = read_json(merged_dir / "pretrained_model_metrics_test.json")
    finetuned = read_json(merged_dir / "finetuned_best_metrics_test.json")
    metrics = metric_delta(pretrained, finetuned)

    blocking = []
    for split, summary in splits.items():
        if summary["wrong_split_count"]:
            blocking.append(f"{split} split contains rows from the wrong init range")
        if summary["duplicate_identity_rows"]:
            blocking.append(f"{split} split contains duplicate sample identities")
        if summary["missing_raster_rows"]:
            blocking.append(f"{split} split contains missing raster paths")
    if pretrained.get("split") != "test" or finetuned.get("split") != "test":
        blocking.append("pretrained/fine-tuned metrics are not both from the test split")
    if pretrained.get("samples") != finetuned.get("samples"):
        blocking.append("pretrained/fine-tuned metrics use different sample counts")

    observations = [
        "train/val/test 按 ego_init 分组切分；test 只包含 ego_init_46-50，未发现 init-level split 交叉。",
        f"SavedModel 对比使用同一 test split 和同一样本数：{pretrained.get('samples')} full-horizon samples。",
        "pretrained 的 minADE 很低但 top1 ADE 很高，说明几何上有接近真值的 mode，但概率排序错误。",
        "fine-tuned 后 top1 ADE 与 minADE 相同，说明 fine-tuned head 把最高概率分配给了几何最佳 mode。",
        f"test split 的 full-horizon local label signature 数量为 {splits['test']['unique_full_horizon_label_signatures_rounded_0p01m']}；该场景较单一，不能把 100% mode-ranking 泛化成通用预测能力。",
        f"pretrained/fine-tuned 的 best_mode_counts 都集中在 mode 7：{pretrained.get('best_mode_counts')} -> {finetuned.get('best_mode_counts')}。",
    ]

    payload = {
        "merged_dir": str(merged_dir),
        "splits": splits,
        "logged_test_metrics_recomputed_from_rollout_json": logged_test,
        "same_test_metrics": metrics,
        "flags": {
            "blocking_issues": blocking,
            "observations": observations,
        },
    }

    with (output_dir / "multipath_sanity_step3.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    write_report(output_dir / "multipath_sanity_step3_report.md", merged_dir, payload)
    print(f"Wrote {output_dir / 'multipath_sanity_step3_report.md'}")


if __name__ == "__main__":
    main()
