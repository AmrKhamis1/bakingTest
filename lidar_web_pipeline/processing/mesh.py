from typing import Literal


def _safe_import_open3d():
	import importlib
	return importlib.import_module("open3d")


def _decimate_to_target_faces(mesh, target_faces: int, logger=None):
	o3d = _safe_import_open3d()
	if len(mesh.triangles) <= target_faces:
		return mesh
	decimated = mesh.simplify_quadric_decimation(target_number_of_triangles=int(target_faces))
	if logger:
		logger.info(f"Decimated from {len(mesh.triangles)} to {len(decimated.triangles)} faces")
	return decimated


def reconstruct_mesh(pcd, method: Literal["poisson","bpa"], poisson_depth: int, target_faces: int, logger=None):
	o3d = _safe_import_open3d()
	pcd.estimate_normals()
	if method == "poisson":
		mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=poisson_depth)
		# Remove low-density triangles
		densities = o3d.utility.DoubleVector(densities)
		density_colors = None
		# Crop to bounding box of points
		bbox = pcd.get_axis_aligned_bounding_box()
		mesh = mesh.crop(bbox)
	else:
		radii = [0.02, 0.04, 0.08]
		mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
			pcd, o3d.utility.DoubleVector(radii)
		)

	mesh.remove_duplicated_vertices()
	mesh.remove_degenerate_triangles()
	mesh.remove_duplicated_triangles()
	mesh.remove_non_manifold_edges()
	mesh.compute_vertex_normals()

	mesh = _decimate_to_target_faces(mesh, target_faces, logger=logger)
	return mesh