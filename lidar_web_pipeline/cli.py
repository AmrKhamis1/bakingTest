import argparse
import os
import time
from dataclasses import dataclass

# Support running as a script or as a module
try:
	from .utils.logging import get_logger
	from .utils.paths import (
		ensure_dir,
		OutputPaths,
	)
	from .io.loaders import load_inputs
	from .registration.register import register_scans_if_needed
	from .processing.clean import clean_point_cloud
	from .processing.mesh import reconstruct_mesh
	from .texturing.pano_extract import extract_panoramas_and_poses
	from .texturing.project_colors import color_mesh_from_panos_or_points
	from .texturing.blender_bake import bake_vertex_colors_and_export
	from .export.package import write_metadata_json
except ImportError:
	import sys as _sys
	import os as _os
	_sys.path.append(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
	from lidar_web_pipeline.utils.logging import get_logger
	from lidar_web_pipeline.utils.paths import (
		ensure_dir,
		OutputPaths,
	)
	from lidar_web_pipeline.io.loaders import load_inputs
	from lidar_web_pipeline.registration.register import register_scans_if_needed
	from lidar_web_pipeline.processing.clean import clean_point_cloud
	from lidar_web_pipeline.processing.mesh import reconstruct_mesh
	from lidar_web_pipeline.texturing.pano_extract import extract_panoramas_and_poses
	from lidar_web_pipeline.texturing.project_colors import color_mesh_from_panos_or_points
	from lidar_web_pipeline.texturing.blender_bake import bake_vertex_colors_and_export
	from lidar_web_pipeline.export.package import write_metadata_json


@dataclass
class PipelineConfig:
	voxel_size: float = 0.02
	outlier_nb_neighbors: int = 20
	outlier_std_ratio: float = 2.0
	poisson_depth: int = 10
	target_faces: int = 500_000
	texture_size: int = 4096
	max_panos_considered: int = 6
	use_gpu: bool = True
	keep_intermediate: bool = False
	meshing_method: str = "poisson"  # or "bpa"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="LiDAR to Web Pipeline")
	parser.add_argument("--input", required=True, help="Path to input file or directory (E57/XYZ/PLY)")
	parser.add_argument("--output", required=True, help="Output directory")
	parser.add_argument("--voxel-size", type=float, default=PipelineConfig.voxel_size)
	parser.add_argument("--outlier-nb-neighbors", type=int, default=PipelineConfig.outlier_nb_neighbors)
	parser.add_argument("--outlier-std-ratio", type=float, default=PipelineConfig.outlier_std_ratio)
	parser.add_argument("--poisson-depth", type=int, default=PipelineConfig.poisson_depth)
	parser.add_argument("--target-faces", type=int, default=PipelineConfig.target_faces)
	parser.add_argument("--texture-size", type=int, default=PipelineConfig.texture_size)
	parser.add_argument("--max-panos-considered", type=int, default=PipelineConfig.max_panos_considered)
	parser.add_argument("--use-gpu", action="store_true", default=PipelineConfig.use_gpu)
	parser.add_argument("--cpu", dest="use_gpu", action="store_false")
	parser.add_argument("--keep-intermediate", action="store_true", default=PipelineConfig.keep_intermediate)
	parser.add_argument("--meshing-method", choices=["poisson", "bpa"], default=PipelineConfig.meshing_method)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	config = PipelineConfig(
		voxel_size=args.voxel_size,
		outlier_nb_neighbors=args.outlier_nb_neighbors,
		outlier_std_ratio=args.outlier_std_ratio,
		poisson_depth=args.poisson_depth,
		target_faces=args.target_faces,
		texture_size=args.texture_size,
		max_panos_considered=args.max_panos_considered,
		use_gpu=args.use_gpu,
		keep_intermediate=args.keep_intermediate,
		meshing_method=args.meshing_method,
	)

	paths = OutputPaths(args.output)
	ensure_dir(paths.base)
	ensure_dir(paths.logs)
	logger = get_logger(os.path.join(paths.logs, "pipeline.log"))
	logger.info("Starting LiDAR to Web pipeline")
	logger.info(f"Config: {config}")

	start_time = time.time()

	logger.info("Loading inputs...")
	loaded = load_inputs(args.input, logger=logger)
	logger.info(f"Loaded {len(loaded.point_clouds)} cloud(s)")

	logger.info("Registering scans if needed...")
	registered_pcd, registered_poses = register_scans_if_needed(loaded, logger=logger)

	logger.info("Cleaning point cloud...")
	cleaned_pcd = clean_point_cloud(
		registered_pcd,
		voxel_size=config.voxel_size,
		outlier_nb_neighbors=config.outlier_nb_neighbors,
		outlier_std_ratio=config.outlier_std_ratio,
		logger=logger,
	)
	if config.keep_intermediate:
		cleaned_path = os.path.join(paths.intermediates, "cleaned.ply")
		ensure_dir(paths.intermediates)
		try:
			import open3d as o3d
			o3d.io.write_point_cloud(cleaned_path, cleaned_pcd)
			logger.info(f"Wrote cleaned point cloud: {cleaned_path}")
		except Exception as e:
			logger.warning(f"Failed to write cleaned point cloud: {e}")

	logger.info("Meshing...")
	mesh = reconstruct_mesh(
		cleaned_pcd,
		method=config.meshing_method,
		poisson_depth=config.poisson_depth,
		target_faces=config.target_faces,
		logger=logger,
	)
	if config.keep_intermediate:
		mesh_path = os.path.join(paths.intermediates, "mesh_raw.ply")
		try:
			import open3d as o3d
			o3d.io.write_triangle_mesh(mesh_path, mesh)
			logger.info(f"Wrote raw mesh: {mesh_path}")
		except Exception as e:
			logger.warning(f"Failed to write raw mesh: {e}")

	logger.info("Extracting panoramas and poses...")
	pano_meta = extract_panoramas_and_poses(loaded, output_dir=paths.panos, logger=logger)
	logger.info(f"Found {len(pano_meta)} panoramas")

	logger.info("Coloring mesh from panos or point colors...")
	colored_mesh = color_mesh_from_panos_or_points(
		mesh=mesh,
		source_pcd=cleaned_pcd,
		pano_meta=pano_meta,
		max_panos_considered=config.max_panos_considered,
		use_gpu=config.use_gpu,
		logger=logger,
	)

	logger.info("Baking and exporting OBJ/MTL...")
	obj_path, mtl_path, texture_path = bake_vertex_colors_and_export(
		colored_mesh,
		textures_dir=paths.textures,
		output_mesh_path=os.path.join(paths.base, "mesh.obj"),
		texture_size=config.texture_size,
		use_gpu=config.use_gpu,
		keep_intermediate=config.keep_intermediate,
		intermediate_dir=paths.intermediates,
		logger=logger,
	)

	logger.info("Writing metadata.json...")
	metadata_path = os.path.join(paths.base, "metadata.json")
	write_metadata_json(
		metadata_path,
		pano_meta=pano_meta,
		obj_path=os.path.relpath(obj_path, paths.base),
		mtl_path=os.path.relpath(mtl_path, paths.base) if mtl_path else None,
		texture_path=os.path.relpath(texture_path, paths.base) if texture_path else None,
		logger=logger,
	)

	elapsed = time.time() - start_time
	logger.info(f"Done in {elapsed/60.0:.1f} min. Outputs in {paths.base}")


if __name__ == "__main__":
	main()