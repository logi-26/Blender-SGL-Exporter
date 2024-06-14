bl_info = {
    "name": "Sega Saturn MDL Exporter",
    "author": "Logi26",
    "version": (1, 1),
    "blender": (2, 78, 0),
    "description": "Exports your model in MDL format for Sega Graphics Library",
    "warning": "",
    "category": "Import-Export",
}

from os import mkdir
from os.path import join, exists, basename, dirname, splitext
from re import sub
import bpy


class MDLExporter(bpy.types.Operator):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL file for SGL"
    filepath = bpy.props.StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        if not mesh_objects:
            print("No objects to process")
            return {'FINISHED'}

        self.filepath = bpy.path.ensure_ext(self.filepath, ".mdl")
        dir_path = dirname(self.filepath)
        base_name = splitext(basename(self.filepath))[0]

        self.export_mdl(mesh_objects, dir_path, base_name)
        CFileWriter(dir_path, base_name).write_c_file()

        if self.model_has_textures(mesh_objects):
            texture_writer = TextureFileWriter(dir_path, base_name)
            texture_writer.write_texture_data()

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def export_mdl(self, mesh_objects, dir_path, base_name):
        mdl_path = join(dir_path, base_name + ".mdl")
        with open(mdl_path, 'w') as mdl_file:
            mdl_file.write("/* Model Name: %s */\n" % base_name)
            mdl_file.write("/* Total Objects: %d */\n" % len(mesh_objects))
            mdl_file.write("/*\n")
            for obj in mesh_objects:
                mdl_file.write("    -%s\n" % self._safe_name(obj.name))
            mdl_file.write("*/\n\n")

            if self._model_has_textures(mesh_objects):
                mdl_file.write('#include "sgl.h"\n')
                mdl_file.write('#include "TEXTURES/%s_DEF.ini"\n' % base_name)
                mdl_file.write("#define GRaddr 0xe000\n\n")

            for obj in mesh_objects:
                try:
                    self._write_object_data(mdl_file, obj)
                except Exception as e:
                    print("Error processing {%s}" % e)

    def _model_has_textures(self, mesh_objects):
        for obj in mesh_objects:
            if obj.data.uv_textures.active:
                for poly in obj.data.polygons:
                    if obj.data.uv_textures.active.data[poly.index].image:
                        return True
        return False

    def _model_has_textures(self, mesh_objects):
        for obj in mesh_objects:
            if obj.data.uv_textures.active:
                for poly in obj.data.polygons:
                    if obj.data.uv_textures.active.data[poly.index].image:
                        return True

    def _safe_name(self, name):
        return sub(r'[^A-Za-z0-9\s]', '', name)

    def _write_object_data(self, mdl_file, obj):
        self._write_vertices(mdl_file, obj)
        self._write_faces_normals(mdl_file, obj)
        self._write_attributes(mdl_file, obj)
        self._write_polygon_data(mdl_file, obj)

    def _write_vertices(self, mdl_file, obj):
        vertices = obj.data.vertices
        mdl_file.write("POINT point_%s[%d] = {\n" % (self._safe_name(obj.name), len(vertices)))
        for vert in vertices:
            x, y, z = vert.co
            mdl_file.write("   POStoFIXED(%9.6f, %9.6f, %9.6f),\n" % (x, y, z))
        mdl_file.write("};\n\n")

    def _write_faces_normals(self, mdl_file, obj):
        polygons = obj.data.polygons
        mdl_file.write("POLYGON polygon_%s[%d] = {\n" % (self._safe_name(obj.name), len(polygons)))
        for poly in polygons:
            if len(poly.vertices) == 4:
                mdl_file.write("   NORMAL(%9.6f, %9.6f, %9.6f), VERTICES(%3d,%3d,%3d,%3d),\n" % (
                    poly.normal.x, poly.normal.y, poly.normal.z,
                    poly.vertices[0], poly.vertices[1], poly.vertices[2], poly.vertices[3]
                ))
            elif len(poly.vertices) == 3:
                mdl_file.write("   NORMAL(%9.6f, %9.6f, %9.6f), VERTICES(%3d,%3d,%3d,%3d),\n" % (
                    poly.normal.x, poly.normal.y, poly.normal.z,
                    poly.vertices[0], poly.vertices[1], poly.vertices[2], poly.vertices[0]
                ))
            else:
                mdl_file.write("//CANNOT CONVERT THIS FACE!\n")
                poly.select = True
        mdl_file.write("};\n\n")

    def _write_attributes(self, mdl_file, obj):
        polygons = obj.data.polygons
        #tex_def = str().join(base_name.split()).upper() + "_TEXNO"
        tex_def = "123"
        texture_id = 0
        mdl_file.write("ATTR attribute_%s[%d] = {\n" % (self._safe_name(obj.name), len(polygons)))
        for poly in polygons:
            r = g = b = 31
            vcol = obj.data.vertex_colors.active
            if vcol:
                for l in poly.loop_indices:
                    r = int(vcol.data[l].color.r * 31)
                    g = int(vcol.data[l].color.g * 31)
                    b = int(vcol.data[l].color.b * 31)

            if obj.data.uv_textures.active and obj.data.uv_textures.active.data[poly.index].image:
                texno = tex_def + "+" + str(texture_id)
                spr = "sprNoflip"
                texture_id += 1
                colno = "CL32KRGB|MESHoff|CL_Gouraud"  
            else:
                texno = "No_Texture"
                spr = "sprPolygon"
                colno = "MESHoff|CL_Gouraud"

            mdl_file.write("   ATTRIBUTE(Single_Plane, SORT_CEN, %s, C_RGB(%d, %d, %d), No_Gouraud, %s, %s, No_Option),\n" % (
                texno, r, g, b, colno, spr
            ))

        mdl_file.write("};\n\n")

    def _write_polygon_data(self, mdl_file, obj):
        obj_name = self._safe_name(obj.name)
        mdl_file.write("VECTOR vector_%s[sizeof(point_%s) / sizeof(POINT)];\n\n" % (obj_name, obj_name))
        mdl_file.write("XPDATA XPD_%s[6] = {\n" % obj_name)
        mdl_file.write("   point_%s, sizeof(point_%s)/sizeof(POINT),\n" % (obj_name, obj_name))
        mdl_file.write("   polygon_%s, sizeof(polygon_%s)/sizeof(POLYGON),\n" % (obj_name, obj_name))
        mdl_file.write("   attribute_%s,\n" % obj_name)
        mdl_file.write("   vector_%s,\n" % obj_name)
        mdl_file.write("};\n\n")


class CFileWriter:
    def __init__(self, dir_path, base_name):
        self.dir_path = dir_path
        self.base_name = base_name

    def write_c_file(self):
        c_path = join(self.dir_path, self.base_name + ".c")
        with open(c_path, 'w') as c_file:
            self._write_includes(c_file)
            self._write_model_properties(c_file)
            self._write_model_draw_functions(c_file)
            self._write_main_draw_function(c_file)
            
    def _safe_name(self, name):
        return sub(r'[^A-Za-z0-9\s]', '', name)

    def _write_includes(self, c_file):
        c_file.write("#include \"%s.mdl\"\n\n" % self.base_name)

    def _write_model_property_declaration(self, c_file, c_name):
        c_file.write("FIXED %s_pos[XYZ];\n" % c_name)
        c_file.write("ANGLE %s_ang[XYZ];\n" % c_name)
        c_file.write("FIXED %s_scl[XYZ];\n\n" % c_name)

    def _write_model_property_initialisation(self, c_file, c_name):
        c_file.write("  // Initialise %s properties\n" % c_name)
        c_file.write("  %s_pos[X] = %s_pos[Y] = %s_pos[Z] = toFIXED(0.0);\n" % (c_name, c_name, c_name))
        c_file.write("  %s_ang[X] = %s_ang[Y] = %s_ang[Z] = DEGtoANG(0.0);\n" % (c_name, c_name, c_name))
        c_file.write("  %s_scl[X] = %s_scl[Y] = %s_scl[Z] = toFIXED(1.0);\n\n" % (c_name, c_name, c_name))

    def _write_model_properties(self, c_file):
        for obj in bpy.data.objects:
            if obj.parent is not None:
                continue

            c_name = self._safe_name(''.join(obj.name.split()).lower())
            c_file.write("// %s model Properties\n" % c_name.capitalize())
            self._write_model_property_declaration(c_file, c_name)

        # Root Matrix Properties
        c_name = self._safe_name(''.join(self.base_name.split()).lower())

        c_file.write("// ROOT MATRIX\n")
        self._write_model_property_declaration(c_file, c_name)

        # Combined initialise function
        c_file.write("void %s_Initialise() {\n" % c_name.capitalize())

        for obj in bpy.data.objects:
            if obj.parent is not None:
                continue

            c_name = self._safe_name(''.join(obj.name.split()).lower())
            self._write_model_property_initialisation(c_file, c_name)

        c_name = self._safe_name(''.join(self.base_name.split()).lower())
        self._write_model_property_initialisation(c_file, c_name)

        c_file.write("}\n\n")

    def _write_transformations(self, c_file, c_name):
        c_file.write("{\n")
        c_file.write("   slPushMatrix();\n")
        c_file.write("   {\n")
        c_file.write("       slTranslate(%s_pos[X], %s_pos[Y], %s_pos[Z]);\n" % (c_name, c_name, c_name))
        c_file.write("       slScale(%s_scl[X], %s_scl[Y], %s_scl[Z]);\n" % (c_name, c_name, c_name))
        c_file.write("       slRotX(%s_ang[X]);\n" % c_name)
        c_file.write("       slRotY(%s_ang[Y]);\n" % c_name)
        c_file.write("       slRotZ(%s_ang[Z]);\n\n" % c_name)
        
    def _write_model_draw_functions(self, c_file):
        for obj in bpy.data.objects:
            if obj.parent is not None:
                continue
            
            c_name = self._safe_name(''.join(obj.name.split()).lower())
            c_file.write("void %s_Draw(FIXED *light)\n" % c_name.capitalize())
            self._write_transformations(c_file, c_name)
            c_file.write("       // Code to draw the object's polygons\n")
            c_file.write("       slPutPolygonX(&XPD_%s, light);\n" % obj.name)
            c_file.write("   }\n")
            c_file.write("   slPopMatrix();\n")
            c_file.write("}\n\n")

    def _write_main_draw_function(self, c_file):
        if self.base_name:
            c_name = self._safe_name(''.join(self.base_name.split()).lower())
            c_file.write("void %s_Draw(FIXED *light)\n" % c_name.capitalize())
            self._write_transformations(c_file, c_name)
            
            # Add the draw function calls for each model
            for obj in bpy.data.objects:
                if obj.parent is not None:
                    continue
                obj_c_name = self._safe_name(''.join(obj.name.split()).lower())
                c_file.write("       %s_Draw(light);\n" % obj_c_name.capitalize())

            c_file.write("   }\n")
            c_file.write("   slPopMatrix();\n")
            c_file.write("}\n\n")


class TextureFileWriter:
    def __init__(self, dir_path, base_name):
        self.dir_path = dir_path
        self.base_name = base_name

    def write_texture_data(self):
        texture_dir = self._create_texture_directory()
        with self._initialize_texture_file(texture_dir) as file:
            texture_id = 0
            tex_table = []
            pic_table = []

            mat, sprite_image, sprite_tex = self._setup_material_and_texture()

            for ob in bpy.data.objects:
                if ob.type == "MESH" and ob.data.uv_textures.active is not None:
                    self._apply_shading_from_mesh(ob)
                    sprite_uv = self._setup_uv_and_material(ob, mat, sprite_tex)
                    new_tex_table, new_pic_table, texture_id = self._bake_sprites(ob, sprite_uv, sprite_image, sprite_tex, file, texture_id)
                    tex_table.extend(new_tex_table)
                    pic_table.extend(new_pic_table)

                    bpy.ops.mesh.uv_texture_remove()
                    bpy.ops.object.select_all(action="DESELECT")

            self._cleanup(mat, sprite_tex, sprite_image)

        self._write_texture_table(texture_dir, tex_table)
        self._write_picture_table(texture_dir, pic_table)
        self._write_picture_def(texture_dir)

    def _create_texture_directory(self):
        texture_dir = join(self.dir_path, "TEXTURES")
        if not exists(texture_dir):
            mkdir(texture_dir)
        return texture_dir

    def _initialize_texture_file(self, texture_dir):
        texture_path = join(texture_dir, self.base_name + ".txr")
        return open(texture_path, 'w')

    def _initialize_texture_table_file(self, texture_dir):
        texture_table_path = join(texture_dir, self.base_name + "_TEX.tbl")
        return open(texture_table_path, 'w')

    def _initialize_picture_table_file(self, texture_dir):
        picture_table_path = join(texture_dir, self.base_name + "._PIC.tbl")
        return open(picture_table_path, 'w')

    def _initialize_picture_def_file(self, texture_dir):
        picture_def_path = join(texture_dir, self.base_name + "._DEF.ini")
        return open(picture_def_path, 'w')

    def _setup_material_and_texture(self):
        mat = bpy.data.materials.new("_tmp")
        sprite_image = bpy.data.images.new("_tmp", 64, 64)
        sprite_tex = bpy.data.textures.new("_tmp", type="IMAGE")
        sprite_tex.image = sprite_image
        return mat, sprite_image, sprite_tex

    def _apply_shading_from_mesh(self, ob):
        # Check the shading type of the mesh faces
        smooth_faces = sum(1 for poly in ob.data.polygons if poly.use_smooth)
        total_faces = len(ob.data.polygons)

        if smooth_faces == total_faces:
            bpy.ops.object.shade_smooth()
        elif smooth_faces == 0:
            bpy.ops.object.shade_flat()
        else:
            # Default to smooth shading if there's a mix of shading types
            bpy.ops.object.shade_smooth()

    def _setup_uv_and_material(self, ob, mat, sprite_tex):
        bpy.ops.object.select_all(action="DESELECT")
        ob.select = True
        bpy.context.scene.objects.active = ob

        sprite_uv = ob.data.uv_textures.new(name="_tmp")
        for tf in ob.data.uv_textures[sprite_uv.name].data:
            tf.image = None

        ob.data.uv_textures[sprite_uv.name].active = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.reset()
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode='OBJECT')

        if ob.data.materials:
            ob.data.materials[0] = mat
        else:
            ob.data.materials.append(mat)

        mat.diffuse_color = (1, 1, 1)
        mat.diffuse_intensity = 1.0

        tex_slot = mat.texture_slots.add()
        tex_slot.texture = sprite_tex
        tex_slot.texture_coords = 'UV'
        tex_slot.uv_layer = ob.data.uv_textures[0].name
        tex_slot.use_map_color_diffuse = True

        sprite_tex.filter_type = "BOX"
        sprite_tex.filter_size = 0.1
        sprite_tex.use_interpolation = False
        sprite_tex.use_mipmap = False

        return sprite_uv

    def _bake_sprites(self, ob, sprite_uv, sprite_image, sprite_tex, file, texture_id):
        tex_table = []
        pic_table = []

        if self._has_lights():
            mat.use_shadeless = False
            bpy.context.scene.render.bake_type = "COMBINED"  # Set to "COMBINED" for lit baking
        else:
            mat.use_shadeless = True
            bpy.context.scene.render.bake_type = "TEXTURE"  # Set to "TEXTURE" for unlit baking

        for i in range(len(ob.data.uv_textures[0].data)):
            if ob.data.uv_textures[0].data[i].image is not None:
                ob.data.uv_textures[sprite_uv.name].data[i].image = sprite_image
                sprite_tex.image = ob.data.uv_textures[0].data[i].image
                bpy.ops.object.bake_image()

                file.write("TEXDAT %s_tex%d[] = {\n" % (ob.name, texture_id))

                pixels = sprite_image.pixels[:]
                for x in range(0, len(pixels), 4):
                    r = int(pixels[x] * 31)
                    g = int(pixels[x + 1] * 31)
                    b = int(pixels[x + 2] * 31)
                    color = (b << 10) | (g << 5) | (r) | 0x8000

                    if x * 0.25 % 8 == 0:
                        file.write("   %s," % (hex(color)))
                    elif x * 0.25 % 8 == 7:
                        file.write("%s,\n" % (hex(color)))
                    else:
                        file.write("%s," % (hex(color)))

                tex_table.append("   TEXDEF(%3d, %3d, CGADDRESS+%9d),\n" % (
                    sprite_image.generated_width,
                    sprite_image.generated_height,
                    ((sprite_image.generated_width * sprite_image.generated_height) * 2) * texture_id
                ))

                pic_table.append("   PICDEF(texdef+%3d, COL_32K, %s_tex%d),\n" % (
                    texture_id,
                    ob.name,
                    texture_id,
                ))

                texture_id += 1
                file.write("};\n\n")

                ob.data.uv_textures[sprite_uv.name].data[i].image = None

        return tex_table, pic_table, texture_id

    def _cleanup(self, mat, sprite_tex, sprite_image):
        mat.texture_slots.clear(0)
        sprite_tex.image = None
        bpy.data.materials.remove(mat, do_unlink=True)
        bpy.data.images.remove(sprite_image)
        bpy.data.textures.remove(sprite_tex)

    def _write_texture_table(self, texture_dir, tex_table):
        with self._initialize_texture_table_file(texture_dir) as texture_table_file:
            texture_table_file.write("// Number of Textures:%9d\n" % len(tex_table))
            if tex_table:
                for t in tex_table:
                    texture_table_file.write(t)
            else:
                texture_table_file.write("// No textures to define!")
            texture_table_file.write("// Include this in a master texture table\n")

    def _write_picture_table(self, texture_dir, pic_table):
        with self._initialize_picture_table_file(texture_dir) as picture_table_file:
            picture_table_file.write("// Number of Pictures:%9d\n" % len(pic_table))
            if pic_table:
                for p in pic_table:
                    picture_table_file.write(p)
            else:
                picture_table_file.write("// No pictures to define!")
            picture_table_file.write("// Include this in a master picture table\n")

    def _write_picture_def(self, texture_dir):
        tex_def = str().join(self.base_name.split()).upper() + "_TEXNO"
        with self._initialize_picture_def_file(texture_dir) as picture_def_file:
            picture_def_file.write("#define %s 0" % tex_def)

    def _has_lights(self):
        return any(obj.type == 'LAMP' for obj in bpy.data.objects)


def menu_func_export(self, context):
    self.layout.operator(MDLExporter.bl_idname, text=MDLExporter.bl_label)

def register():
    bpy.utils.register_class(MDLExporter)
    bpy.types.INFO_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(MDLExporter)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()