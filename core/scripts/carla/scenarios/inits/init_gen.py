import json
from pathlib import Path

import numpy as np


OUT_DIR = Path(__file__).resolve().parent


def main():
    # Match the upstream SMPC_MMPreds intersection initial-condition sweep.
    rng = np.random.default_rng(123)
    vel_inits = 9.0 + (rng.random(50) - 0.5) * 2
    long_inits = (rng.random(50) - 0.5) * 5

    for i in range(50):
        json_name = f"ego_init_{i + 1:02d}.json"
        init_dict = {
            "start_longitudinal_offset": float(long_inits[i]),
            "init_speed": float(vel_inits[i]),
        }
        with open(OUT_DIR / json_name, "w") as outfile:
            json.dump(init_dict, outfile)


if __name__ == "__main__":
    main()
