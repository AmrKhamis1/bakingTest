from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import os


def _safe_import_open3d():
	import importlib
	return importlib.import_module("open3d")


@dataclass
class LoadedInputs:
	point_clouds: list
	poses: Optional[List]
	aux: Dict[str, Any]


def _load_xyz_or_ply(path: str):
	o3d = _safe_import_open3d()
	pcd = o3d.io.read_point_cloud(path)
	return [pcd], None, {"type": "xyz_or_ply", "source": path}


def _load_e57(path: str, logger=None):
	try:
		import pye57
	except Exception as e:
		if logger:
			logger.warning(f"pye57 not available: {e}. Falling back to PDAL if possible.")
			return _load_e57_with_pdal(path, logger=logger)
		else:
			return _load_e57_with_pdal(path, logger=None)

	reader = pye57.E57(path)
	scans = reader.scans
	clouds = []
	poses = []
	for i, scan in enumerate(scans):
		xyz = scan.cartesian
		o3d = _safe_import_open3d()
		pcd = o3d.geometry.PointCloud()
		pcd.points = o3d.utility.Vector3dVector(xyz)
		if scan.color is not None:
			pcd.colors = o3d.utility.Vector3dVector(scan.color / 255.0)
		clouds.append(pcd)
		pose = getattr(scan, "pose", None)
		poses.append(pose)

	aux = {"type": "e57", "reader": reader}
	return clouds, poses, aux


def _load_e57_with_pdal(path: str, logger=None):
	try:
		import pdal
		import numpy as np
	except Exception as e:
		raise RuntimeError("Neither pye57 nor PDAL available to read E57") from e

	pipeline_json = f"""
	{{
	  "pipeline": [
	    {{"type":"readers.e57","filename":"{path}"}}
	  ]
	}}
	"""
	pipe = pdal.Pipeline(pipeline_json)
	pipe.execute()
	arrays = pipe.arrays
	clouds = []
	poses = []
	o3d = _safe_import_open3d()
	for arr in arrays:
		X = arr['X'].astype(float)
		Y = arr['Y'].astype(float)
		Z = arr['Z'].astype(float)
		pts = np.stack([X, Y, Z], axis=1)
		pcd = o3d.geometry.PointCloud()
		pcd.points = o3d.utility.Vector3dVector(pts)
		if set(['Red','Green','Blue']).issubset(arr.dtype.names):
			R = arr['Red'].astype(float)
			G = arr['Green'].astype(float)
			B = arr['Blue'].astype(float)
			cols = np.stack([R,G,B], axis=1) / 255.0
			pcd.colors = o3d.utility.Vector3dVector(cols)
		clouds.append(pcd)
		poses.append(None)

	aux = {"type": "e57", "pdal": pipe}
	return clouds, poses, aux


def load_inputs(path: str, logger=None) -> LoadedInputs:
	path = os.path.abspath(path)
	if os.path.isdir(path):
		clouds = []
		for name in sorted(os.listdir(path)):
			low = name.lower()
			if low.endswith(".ply") or low.endswith(".xyz") or low.endswith(".pcd"):
				pcs, _, _ = _load_xyz_or_ply(os.path.join(path, name))
				clouds.extend(pcs)
		return LoadedInputs(point_clouds=clouds, poses=None, aux={"type": "folder", "root": path})
	else:
		low = path.lower()
		if low.endswith(".e57"):
			c, p, aux = _load_e57(path, logger=logger)
			return LoadedInputs(point_clouds=c, poses=p, aux=aux)
		elif low.endswith((".ply", ".xyz", ".pcd")):
			c, p, aux = _load_xyz_or_ply(path)
			return LoadedInputs(point_clouds=c, poses=p, aux=aux)
		else:
			raise ValueError(f"Unsupported input: {path}")