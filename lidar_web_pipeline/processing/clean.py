from typing import Optional


def _safe_import_open3d():
	import importlib
	return importlib.import_module("open3d")


def clean_point_cloud(pcd, voxel_size: float, outlier_nb_neighbors: int, outlier_std_ratio: float, logger=None):
	o3d = _safe_import_open3d()
	if voxel_size and voxel_size > 0:
		pcd = pcd.voxel_down_sample(voxel_size)
		if logger:
			logger.info(f"Downsampled with voxel={voxel_size}")

	pcd.estimate_normals()
	pcd, ind = pcd.remove_statistical_outlier(nb_neighbors=outlier_nb_neighbors, std_ratio=outlier_std_ratio)
	if logger:
		logger.info(f"Removed outliers: kept {len(ind)} points")

	return pcd