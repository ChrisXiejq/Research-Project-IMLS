#!/usr/bin/env python3
"""
Assemble a runnable reproduction workspace in Research-Project-IMLS
from local source repositories:
  - SMPC_MMPreds
  - confidence_aware_predictions
"""

from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC_BASE = ROOT.parent

SRC_SMPC = SRC_BASE / "SMPC_MMPreds"
SRC_CAP = SRC_BASE / "confidence_aware_predictions"

TARGET_CORE = ROOT / "core"
TARGET_EXT = ROOT / "extensions"
TARGET_DOCS = ROOT / "docs"


def rm_if_exists(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing source: {src}")
    rm_if_exists(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing source: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    # Clean old assembled folders
    for p in [TARGET_CORE, TARGET_EXT, TARGET_DOCS]:
        rm_if_exists(p)
        p.mkdir(parents=True, exist_ok=True)

    # ---- Core baseline reproduction (from SMPC_MMPreds) ----
    copy_tree(SRC_SMPC / "env_setup", TARGET_CORE / "env_setup")
    copy_tree(SRC_SMPC / "scripts", TARGET_CORE / "scripts")
    copy_tree(SRC_SMPC / "results", TARGET_CORE / "results_template")
    copy_file(SRC_SMPC / "README.md", TARGET_CORE / "README.upstream.md")
    copy_file(SRC_SMPC / "LICENSE", TARGET_CORE / "LICENSE.upstream")

    # Keep AutoDL environment patch if present
    autodl_env = SRC_SMPC / "env_setup" / "environment.autodl.yml"
    if autodl_env.exists():
        copy_file(autodl_env, TARGET_CORE / "env_setup" / "environment.autodl.yml")

    # ---- Optional extension references (from confidence repo) ----
    # Keep only modules useful for prediction-side extensions (calibration etc.)
    copy_tree(SRC_CAP / "scripts" / "models", TARGET_EXT / "confidence_models")
    copy_tree(SRC_CAP / "scripts" / "evaluation", TARGET_EXT / "confidence_evaluation")
    copy_tree(SRC_CAP / "scripts" / "carla" / "policies", TARGET_EXT / "confidence_policies")
    copy_tree(SRC_CAP / "data", TARGET_EXT / "confidence_data")
    copy_file(SRC_CAP / "README.md", TARGET_EXT / "README.confidence_upstream.md")

    # ---- Docs ----
    copy_file(
        SRC_BASE / "AutoDL_SMPC_MMPreds_保守复现环境手册.md",
        TARGET_DOCS / "AutoDL_Environment_Setup.md",
    )

    print("Assemble completed.")
    print(f"Core: {TARGET_CORE}")
    print(f"Extensions: {TARGET_EXT}")
    print(f"Docs: {TARGET_DOCS}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[assemble] failed: {e}", file=sys.stderr)
        raise

