"""
Batch + per-scenario experiment logging.

Writes under the same timestamp directory as ``scenario_result.pkl`` siblings:
  - ``experiment_run.log`` — human-readable trace (batch + subruns)
  - ``environment.json`` — Python / key packages / env flags (no secrets)
  - ``batch_events.jsonl`` — one JSON object per line for automated checks
  - ``batch_subruns.json`` — list of subruns (written at batch end; includes ``metrics`` when pkl present)
  - ``batch_summary.txt`` — one screen-friendly table: success + ego feasibility etc. (batch end)
  - ``<savedir>/scenario_run_summary.json`` — per-rollout aggregates + errors
  - ``<savedir>/scenario_steps.csv`` — per-step metrics for reproducibility review
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

LOGGER_NAME = "imls.experiment"
_state: Dict[str, Any] = {"configured": False, "batch_dir": None}


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        if obj.size > 256 and obj.ndim == 1:
            return {"__ndarray__": "truncated", "shape": list(obj.shape), "head": obj[:32].tolist()}
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, (bool, int, str)) or obj is None:
        return obj
    return str(obj)


def collect_environment_snapshot() -> Dict[str, Any]:
    snap: Dict[str, Any] = {
        "utc_iso": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "env": {},
    }
    for key in (
        "CARLA_ROOT",
        "GUROBI_HOME",
        "GUROBI_VERSION",
        "GRB_LICENSE_FILE",
        "CUDA_VISIBLE_DEVICES",
        "IMLS_LOG_LEVEL",
    ):
        val = os.environ.get(key)
        if val is not None:
            if key == "GRB_LICENSE_FILE":
                snap["env"][key] = os.path.basename(val)
            else:
                snap["env"][key] = val
    for mod in ("tensorflow", "casadi", "carla"):
        try:
            m = __import__(mod)
            snap[mod] = str(getattr(m, "__version__", "?"))
        except Exception as e:
            snap[mod] = f"import_failed: {e}"
    try:
        import gurobipy as gp

        snap["gurobipy"] = str(gp.gurobi.version())
    except Exception as e:
        snap["gurobipy"] = f"import_failed: {e}"
    return snap


def write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_to_jsonable(data), f, indent=2, ensure_ascii=False)


def append_jsonl(batch_dir: str, record: Dict[str, Any]) -> None:
    path = os.path.join(batch_dir, "batch_events.jsonl")
    line = json.dumps(_to_jsonable(record), ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure_batch_logging(
    batch_results_dir: str,
    *,
    console: bool = True,
    file_level: int = logging.INFO,
) -> logging.Logger:
    """
    Attach file + optional console handlers to ``imls.experiment`` and children.
    Safe to call once per process; removes prior handlers on this logger.
    """
    batch_results_dir = os.path.abspath(batch_results_dir)
    os.makedirs(batch_results_dir, exist_ok=True)
    _state["batch_dir"] = batch_results_dir
    _state["configured"] = True

    log_path = os.path.join(batch_results_dir, "experiment_run.log")
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(file_level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(file_level)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    logging.captureWarnings(True)
    py_warnings = logging.getLogger("py.warnings")
    py_warnings.addHandler(fh)
    if console:
        py_warnings.addHandler(ch)

    write_json(os.path.join(batch_results_dir, "environment.json"), collect_environment_snapshot())
    append_jsonl(
        batch_results_dir,
        {
            "event": "logging_configured",
            "batch_dir": batch_results_dir,
            "log_file": log_path,
        },
    )
    logger.info("Experiment logging initialized; batch_dir=%s", batch_results_dir)
    return logger


def batch_dir() -> Optional[str]:
    return _state.get("batch_dir")


def summarize_results_arrays(results_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight stats from the same structure as ``scenario_result.pkl``."""
    out: Dict[str, Any] = {}
    for act_key, payload in results_dict.items():
        block: Dict[str, Any] = {}
        feas = payload.get("feasibility")
        st = payload.get("solve_times")
        if feas is not None and len(feas) > 0:
            arr = np.asarray(feas)
            block["n_steps"] = int(arr.shape[0])
            if arr.dtype == bool or np.issubdtype(arr.dtype, np.integer):
                block["feasible_frac"] = float(np.mean(arr.astype(float)))
            else:
                block["feasible_frac"] = float(np.nanmean(arr.astype(float)))
        if st is not None and len(st) > 0:
            arr = np.asarray(st, dtype=float)
            block["solve_time_mean"] = float(np.nanmean(arr))
            block["solve_time_max"] = float(np.nanmax(arr))
            block["solve_time_nan_frac"] = float(np.mean(np.isnan(arr)))
        traj = payload.get("state_trajectory")
        if traj is not None and len(traj) > 0:
            block["state_rows"] = int(np.asarray(traj).shape[0])
        out[act_key] = block
    return out


def collect_savedir_metrics(savedir: str) -> Dict[str, Any]:
    """
    Read ``scenario_result.pkl`` under ``savedir`` and return compact stats
    (feasible_frac, n_steps, solve_time stats per actor). Safe if pkl missing or corrupt.
    """
    pkl = os.path.join(savedir, "scenario_result.pkl")
    out: Dict[str, Any] = {
        "pkl_path": os.path.abspath(pkl),
        "pkl_exists": os.path.isfile(pkl),
    }
    if not out["pkl_exists"]:
        return out
    try:
        with open(pkl, "rb") as f:
            results_dict = pickle.load(f)
        out["actors"] = summarize_results_arrays(results_dict)
        ego_keys = [k for k in out["actors"] if str(k).startswith("ego")]
        if ego_keys:
            # Prefer lowest-index ego (ego_0 before ego_3) for a single headline number.
            ego_keys_sorted = sorted(
                ego_keys,
                key=lambda s: int(str(s).split("_")[-1]) if str(s).split("_")[-1].isdigit() else 0,
            )
            ek = ego_keys_sorted[0]
            blk = out["actors"][ek]
            out["ego_primary_key"] = ek
            out["ego_n_steps"] = blk.get("n_steps")
            out["ego_feasible_frac"] = blk.get("feasible_frac")
            out["ego_solve_time_mean"] = blk.get("solve_time_mean")
            out["ego_solve_time_nan_frac"] = blk.get("solve_time_nan_frac")
    except Exception as e:
        out["pkl_error"] = repr(e)
    return out


def write_scenario_run_summary(
    savedir: str,
    *,
    scenario_kind: str,
    ran_successfully: bool,
    max_iters: int,
    carla_fps: float,
    results_dict: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {
        "scenario_kind": scenario_kind,
        "savedir": os.path.abspath(savedir),
        "ran_successfully": ran_successfully,
        "max_iters": max_iters,
        "carla_fps": carla_fps,
        "utc_iso": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        payload["error"] = error
    if results_dict is not None:
        payload["stats"] = summarize_results_arrays(results_dict)
    if extra:
        payload["extra"] = _to_jsonable(extra)
    write_json(os.path.join(savedir, "scenario_run_summary.json"), payload)


def append_step_row(
    savedir: str,
    rows_buffer: List[Dict[str, Any]],
    row: Dict[str, Any],
    *,
    flush_every: int = 20,
) -> None:
    rows_buffer.append(row)
    if len(rows_buffer) >= flush_every:
        flush_step_csv(savedir, rows_buffer)


def flush_step_csv(savedir: str, rows_buffer: List[Dict[str, Any]]) -> None:
    if not rows_buffer:
        return
    import csv

    path = os.path.join(savedir, "scenario_steps.csv")
    keys = sorted({k for r in rows_buffer for k in r.keys()})
    newfile = not os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        if newfile:
            w.writeheader()
        for r in rows_buffer:
            w.writerow({k: r.get(k, "") for k in keys})
    rows_buffer.clear()


def log_batch_subrun(
    label: str,
    *,
    phase: str,
    duration_s: float,
    ok: bool,
    error: Optional[str] = None,
    savedir: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> None:
    logger = get_logger()
    msg = f"[{phase}] {label} duration_s={duration_s:.3f} ok={ok}"
    if metrics and metrics.get("pkl_exists"):
        eg = metrics.get("ego_feasible_frac")
        ns = metrics.get("ego_n_steps")
        if eg is not None:
            msg += f" ego_feasible_frac={eg:.4f}"
        if ns is not None:
            msg += f" ego_n_steps={ns}"
    if error:
        msg += f" error={error}"
    if ok:
        logger.info(msg)
    else:
        logger.error(msg)
    bd = batch_dir()
    if bd:
        rec: Dict[str, Any] = {
            "event": "subrun_end",
            "phase": phase,
            "label": label,
            "duration_s": duration_s,
            "ok": ok,
        }
        if savedir:
            rec["savedir"] = os.path.abspath(savedir)
        if error:
            rec["error"] = error
        if metrics:
            rec["metrics"] = _to_jsonable(metrics)
        append_jsonl(bd, rec)


def _fmt_opt_float(x: Any) -> str:
    if x is None:
        return ""
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return ""
    if xf != xf:  # NaN
        return "nan"
    return f"{xf:.6f}"


def write_batch_summary_txt(batch_dir: str, subruns: List[Dict[str, Any]]) -> str:
    """
    Write ``batch_summary.txt`` with one line per subrun (tab-separated for easy grep).
    Returns path written.
    """
    path = os.path.join(os.path.abspath(batch_dir), "batch_summary.txt")
    lines = []
    lines.append("# IMLS batch summary (auto-generated)")
    lines.append(
        "# columns: ok scenario_completed duration_s label ego_n_steps ego_feasible_frac ego_solve_t_mean pkl_exists"
    )
    lines.append("")
    for s in subruns:
        m = s.get("metrics") or {}
        lines.append(
            "\t".join(
                [
                    "1" if s.get("ok") else "0",
                    "1"
                    if s.get("scenario_completed") is True
                    else ("0" if s.get("scenario_completed") is False else "?"),
                    f"{float(s.get('duration_s', 0.0)):.3f}",
                    str(s.get("label", "")),
                    str(m.get("ego_n_steps", "")),
                    ""
                    if m.get("ego_feasible_frac") is None
                    else f"{float(m['ego_feasible_frac']):.6f}",
                    _fmt_opt_float(m.get("ego_solve_time_mean")),
                    "1" if m.get("pkl_exists") else "0",
                ]
            )
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    append_jsonl(
        batch_dir,
        {"event": "batch_summary_written", "path": path, "n_subruns": len(subruns)},
    )
    get_logger().info("Wrote batch summary: %s (%d subruns)", path, len(subruns))
    return path
