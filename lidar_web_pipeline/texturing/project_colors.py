from typing import List, Dict, Any
import math
import os


def _safe_import_open3d():
	import importlib
	return importlib.import_module("open3d")


def _load_images(pano_meta: List[Dict[str, Any]]):
	from PIL import Image
	imgs = []
	for p in pano_meta:
		path = p.get("file")
		if not path or not os.path.exists(path):
			imgs.append(None)
			continue
		img = Image.open(path).convert("RGB")
		imgs.append(img)
	return imgs


def _rotation_matrix_from_meta(rot_meta):
	import numpy as np
	if rot_meta is None:
		return np.eye(3)
	rot = np.array(rot_meta)
	if rot.shape == (3,3):
		return rot
	if rot.shape == (4,4):
		return rot[:3,:3]
	return np.eye(3)


def _dir_to_equirect_uv(dir_cam, width, height):
	# dir_cam is unit vector in camera frame
	x, y, z = dir_cam
	yaw = math.atan2(x, z)  # [-pi, pi]
	pitch = math.asin(max(-1.0, min(1.0, y)))  # [-pi/2, pi/2]
	u = (yaw / (2 * math.pi) + 0.5) * width
	v = (0.5 - pitch / math.pi) * height
	return int(max(0, min(width - 1, round(u)))), int(max(0, min(height - 1, round(v))))


def _build_raycast_scene(mesh, logger=None):
	try:
		import open3d as o3d
		tmesh = o3d.t.geometry.TriangleMesh.from_legacy(mesh)
		scene = o3d.t.geometry.RaycastingScene()
		scene.add_triangles(tmesh)
		return scene
	except Exception as e:
		if logger:
			logger.warning(f"RaycastingScene unavailable: {e}. Occlusion checks disabled.")
		return None


def color_mesh_from_panos_or_points(mesh, source_pcd, pano_meta: List[Dict[str,Any]], max_panos_considered: int, use_gpu: bool, logger=None):
	import numpy as np
	o3d = _safe_import_open3d()
	# If no panos, color from point cloud nearest neighbor
	if not pano_meta:
		if logger:
			logger.info("No panos. Coloring mesh by nearest point colors (approx)")
		kdtree = o3d.geometry.KDTreeFlann(source_pcd)
		vcols = []
		sp = np.asarray(source_pcd.points)
		if source_pcd.has_colors():
			sc = np.asarray(source_pcd.colors)
		else:
			sc = None
		for v in np.asarray(mesh.vertices):
			_, idxs, _ = kdtree.search_knn_vector_3d(v, 1)
			if sc is not None:
				vcols.append(sc[idxs[0]])
			else:
				vcols.append([0.7, 0.7, 0.7])
		mesh.vertex_colors = o3d.utility.Vector3dVector(vcols)
		return mesh

	# Pano-based projection
	imgs = _load_images(pano_meta)
	cam_positions = []
	rotations = []
	for p in pano_meta:
		pos = p.get("position")
		if pos is None:
			cam_positions.append(None)
		else:
			cam_positions.append(np.array(pos, dtype=float))
		rotations.append(_rotation_matrix_from_meta(p.get("rotation")))

	scene = _build_raycast_scene(mesh, logger=logger)
	vertices = np.asarray(mesh.vertices)
	num_vertices = vertices.shape[0]
	use_occlusion = scene is not None and num_vertices <= 300000
	if logger:
		logger.info(f"Projecting colors from {len(imgs)} panos. Occlusion={'on' if use_occlusion else 'off'}; vertices={num_vertices}")

	vcols = np.zeros((num_vertices, 3), dtype=np.float64)
	valid = np.zeros((num_vertices,), dtype=bool)

	for vi, v in enumerate(vertices):
		best_col = None
		best_score = -1e9
		# Choose nearest K cameras with known positions
		dists = []
		for i, cpos in enumerate(cam_positions):
			if cpos is None or imgs[i] is None:
				dists.append(float('inf'))
				continue
				dists.append(np.linalg.norm(v - cpos))
		order = np.argsort(dists)[:max_panos_considered]
		for i in order:
			cpos = cam_positions[i]
			if not np.isfinite(dists[i]) or cpos is None:
				continue
			img = imgs[i]
			R = rotations[i]
			dir_vec = v - cpos
			dist = np.linalg.norm(dir_vec)
			if dist < 1e-6:
				continue
			dir_vec /= dist
			# Occlusion check
			if use_occlusion:
				# open3d.t expects rays tensor with origin+direction
				import open3d as o3d
				origin = cpos.astype(np.float32)
				dirf = dir_vec.astype(np.float32)
				rays = o3d.core.Tensor([[origin[0], origin[1], origin[2], dirf[0], dirf[1], dirf[2]]], dtype=o3d.core.Dtype.Float32)
				hits = scene.cast_rays(rays)
				thit = float(hits['t_hit'].numpy()[0])
				if math.isfinite(thit) and thit + 1e-3 < dist:
					continue  # occluded
			# Transform to camera frame
			dir_cam = R.T @ dir_vec
			u, vpx = _dir_to_equirect_uv(dir_cam, img.width, img.height)
			col = np.array(img.getpixel((u, vpx))) / 255.0
			# Prefer closer and more frontal
			score = -dist + dir_cam[2]  # z forward
			if score > best_score:
				best_score = score
				best_col = col
		if best_col is not None:
			vcols[vi] = best_col
			valid[vi] = True
		else:
			vcols[vi] = [0.8, 0.8, 0.8]

	mesh.vertex_colors = o3d.utility.Vector3dVector(vcols.tolist())
	return mesh