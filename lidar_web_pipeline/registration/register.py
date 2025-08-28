from typing import Optional, List, Tuple
import numpy as np


def _safe_import_open3d():
	import importlib
	return importlib.import_module("open3d")


class _PoseUtils:
	@staticmethod
	def compose_clouds_with_poses(clouds, poses):
		o3d = _safe_import_open3d()
		assert len(clouds) == len(poses)
		accum = o3d.geometry.PointCloud()
		for pcd, pose in zip(clouds, poses):
			pcd_t = pcd.transform(pose.copy()) if pose is not None else pcd
			accum += pcd_t
		return accum


class _ICPRegister:
	def __init__(self):
		self.o3d = _safe_import_open3d()

	def register(self, clouds) -> Tuple[object, List[np.ndarray]]:
		if not clouds:
			raise ValueError("No clouds to register")
		poses = [np.eye(4)]
		accum = clouds[0].clone()
		voxel = 0.05
		source_down = accum.voxel_down_sample(voxel)
		source_down.estimate_normals()
		for idx in range(1, len(clouds)):
			target = clouds[idx]
			target_down = target.voxel_down_sample(voxel)
			target_down.estimate_normals()
			reg = self.o3d.pipelines.registration.registration_icp(
				target_down, source_down, 0.2,
				np.eye(4),
				self.o3d.pipelines.registration.TransformationEstimationPointToPlane(),
			)
			T = reg.transformation
			poses.append(T @ poses[-1])
			accum += target.transform(T)
			source_down = accum.voxel_down_sample(voxel)
			source_down.estimate_normals()
		return accum, poses


def register_scans_if_needed(loaded_inputs, logger=None):
	clouds = loaded_inputs.point_clouds
	poses = loaded_inputs.poses
	if poses and any(p is not None for p in poses):
		if logger:
			logger.info("Using provided poses for registration")
		return _PoseUtils.compose_clouds_with_poses(clouds, poses), poses
	else:
		if logger:
			logger.info("Running ICP registration")
		reg = _ICPRegister()
		return reg.register(clouds)