import json
import random
from pathlib import Path



rng=random.Random(123)
vel_inits=[9.0+(rng.random()-0.5)*2 for _ in range(50)]
long_inits=[0.0+(rng.random()-0.5)*10 for _ in range(50)]
out_dir = Path(__file__).resolve().parent


init_dict={"start_longitudinal_offset" : 0.0, "init_speed" : 0.0}


for i in range(50):
	if i<=8:
		json_name=f"ego_init_0{i+1}.json"
	else:
		json_name=f"ego_init_{i+1}.json"
	init_dict["start_longitudinal_offset"]=long_inits[i]
	init_dict["init_speed"]=vel_inits[i]
	with open(out_dir / json_name, "w") as outfile:
		json.dump(init_dict, outfile)



