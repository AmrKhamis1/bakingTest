import json
from typing import List, Dict, Any, Optional


def write_metadata_json(path: str, pano_meta: List[Dict[str, Any]], obj_path: str, mtl_path: Optional[str], texture_path: Optional[str], logger=None) -> None:
	meta = {
		"mesh": {
			"obj": obj_path,
			"mtl": mtl_path,
			"texture": texture_path,
		},
		"panoramas": [
			{
				"file": p.get("file"),
				"position": p.get("position"),
				"rotation": p.get("rotation"),
			}
			for p in pano_meta
		],
	}
	with open(path, 'w') as f:
		json.dump(meta, f, indent=2)
	if logger:
		logger.info(f"Wrote metadata: {path}")