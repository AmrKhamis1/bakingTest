from typing import List, Dict, Any
import os


def _ensure_dir(path: str) -> None:
	os.makedirs(path, exist_ok=True)


def _save_image_np(path: str, img):
	from PIL import Image
	Image.fromarray(img).save(path, quality=92)


def _copy_or_convert_image(src_path: str, dst_path: str):
	from PIL import Image
	try:
		im = Image.open(src_path).convert('RGB')
		im.save(dst_path, quality=92)
	except Exception:
		# fallback: copy
		import shutil
		shutil.copy2(src_path, dst_path)


def extract_panoramas_and_poses(loaded_inputs, output_dir: str, logger=None) -> List[Dict[str, Any]]:
	_ensure_dir(output_dir)
	meta: List[Dict[str, Any]] = []
	aux = loaded_inputs.aux or {}
	# E57 path via pye57
	if aux.get("type") == "e57" and "reader" in aux:
		try:
			import numpy as np
			reader = aux["reader"]
			for idx, scan in enumerate(reader.scans):
				pose = getattr(scan, "pose", None)
				R = pose[:3,:3].tolist() if pose is not None else None
				T = pose[:3,3].tolist() if pose is not None else None
				# Prefer spherical_images list
				imgs = []
				if getattr(scan, "spherical_images", None):
					for p_idx, pano in enumerate(scan.spherical_images):
						img = pano.image  # numpy array HxWx3 uint8
						fname = f"pano_{idx:03d}_{p_idx:02d}.jpg"
						fpath = os.path.join(output_dir, fname)
						_save_image_np(fpath, img)
						meta.append({
							"file": fpath,
							"position": T,
							"rotation": R,
						})
				elif getattr(scan, "panorama", None) is not None:
					img = scan.panorama
					fname = f"pano_{idx:03d}.jpg"
					fpath = os.path.join(output_dir, fname)
					_save_image_np(fpath, img)
					meta.append({
						"file": fpath,
						"position": T,
						"rotation": R,
					})
			if logger:
				logger.info(f"Extracted {len(meta)} panoramas from E57")
		except Exception as e:
			if logger:
				logger.warning(f"Failed to read panoramas from E57: {e}")
			# continue to folder fallback
	# Folder fallback: look for images in input directory
	if aux.get("type") == "folder" and aux.get("root"):
		root = aux["root"]
		images = []
		for name in sorted(os.listdir(root)):
			low = name.lower()
			if low.endswith((".jpg",".jpeg",".png")) and not low.startswith("._"):
				images.append(os.path.join(root, name))
		pano_dir = os.path.join(root, "panos")
		if os.path.isdir(pano_dir):
			for name in sorted(os.listdir(pano_dir)):
				low = name.lower()
				if low.endswith((".jpg",".jpeg",".png")):
					images.append(os.path.join(pano_dir, name))
		for i, src in enumerate(images):
			fname = f"pano_{i:03d}.jpg"
			fpath = os.path.join(output_dir, fname)
			_copy_or_convert_image(src, fpath)
			meta.append({"file": fpath, "position": None, "rotation": None})
		if logger and images:
			logger.info(f"Collected {len(images)} panorama image(s) from folder inputs")
	return meta