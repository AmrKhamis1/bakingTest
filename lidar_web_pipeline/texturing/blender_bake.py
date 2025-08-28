import os
import subprocess
import tempfile

BLENDER_SCRIPT = r"""
import bpy, sys, os

argv = sys.argv
argv = argv[argv.index('--') + 1:] if '--' in argv else []
output_mesh_path = argv[0]
texture_path = argv[1]
texture_size = int(argv[2])
use_gpu = argv[3] == '1'
intermediate_dir = argv[4]

# Clear scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import PLY from stdin path
mesh_path = os.path.join(intermediate_dir, 'mesh_for_blender.ply')
bpy.ops.import_mesh.ply(filepath=mesh_path)
obj = bpy.context.selected_objects[0]
mesh = obj.data

# Ensure UV map
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=66.0)
bpy.ops.object.mode_set(mode='OBJECT')

# Create image
img = bpy.data.images.new('Albedo', width=texture_size, height=texture_size, alpha=False, float_buffer=False)
img.filepath_raw = texture_path
img.file_format = 'PNG'

# Create material that uses vertex colors (Col) and bake to image
mat = bpy.data.materials.new('BakeMat')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
for n in list(nodes):
    nodes.remove(n)

out = nodes.new('ShaderNodeOutputMaterial')
diffuse = nodes.new('ShaderNodeBsdfDiffuse')
vcol = nodes.new('ShaderNodeVertexColor')
vcol.layer_name = obj.data.vertex_colors[0].name if obj.data.vertex_colors else ''
teximg = nodes.new('ShaderNodeTexImage')
teximg.image = img
links.new(vcol.outputs['Color'], diffuse.inputs['Color'])
links.new(diffuse.outputs['BSDF'], out.inputs['Surface'])

obj.data.materials.clear()
obj.data.materials.append(mat)

# Bake diffuse color
for o in bpy.data.objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        break

bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'GPU' if use_gpu else 'CPU'
bpy.context.scene.cycles.samples = 1

# Set bake target image
for node in obj.active_material.node_tree.nodes:
    if node.type == 'TEX_IMAGE':
        node.select = True
        obj.active_material.node_tree.nodes.active = node
        break

bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'})
img.save()

# Export OBJ
bpy.ops.export_scene.obj(filepath=output_mesh_path, use_materials=True, path_mode='AUTO')
"""


def bake_vertex_colors_and_export(mesh_o3d, textures_dir: str, output_mesh_path: str, texture_size: int, use_gpu: bool, keep_intermediate: bool, intermediate_dir: str, logger=None):
	import open3d as o3d
	os.makedirs(textures_dir, exist_ok=True)
	os.makedirs(intermediate_dir, exist_ok=True)

	# Save mesh for Blender as PLY with vertex colors
	mesh_for_blender = os.path.join(intermediate_dir, 'mesh_for_blender.ply')
	o3d.io.write_triangle_mesh(mesh_for_blender, mesh_o3d)

	texture_path = os.path.join(textures_dir, f'albedo_{texture_size}.png')

	# Write the blender script to temp file
	bl_script = os.path.join(intermediate_dir, 'bake.py')
	with open(bl_script, 'w') as f:
		f.write(BLENDER_SCRIPT)

	cmd = [
		"blender", "-b", "-P", bl_script, "--",
		output_mesh_path,
		texture_path,
		str(texture_size),
		"1" if use_gpu else "0",
		intermediate_dir,
	]
	if logger:
		logger.info("Running Blender bake ...")
	try:
		subprocess.run(cmd, check=True)
	except Exception as e:
		if logger:
			logger.warning(f"Blender bake failed: {e}. Exporting OBJ without texture.")
		# fallback: export OBJ from Open3D
		mtl_path = None
		texture_path = None
		obj_path = output_mesh_path
		try:
			o3d.io.write_triangle_mesh(output_mesh_path, mesh_o3d)
		except Exception:
			pass
		return obj_path, mtl_path, texture_path

	# Blender writes OBJ and MTL side-by-side
	obj_path = output_mesh_path
	mtl_path = os.path.splitext(output_mesh_path)[0] + ".mtl"
	return obj_path, mtl_path, texture_path