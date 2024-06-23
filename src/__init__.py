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
from bpy.types import Operator

GENERATE_LOG_FILE = True

class BaseExporter:
    def _safe_name(self, name):
        return sub(r'[^A-Za-z0-9\s]', '', name)


class MDLExporter(Operator, BaseExporter):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL file for SGL"
    filepath = bpy.props.StringProperty(subtype='FILE_PATH')
    texture_id = 0

    def execute(self, context):
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        
        # Exit script if no mesh objects are found
        if not mesh_objects:
            print("No objects to process")
            return {'FINISHED'}

        self.filepath = bpy.path.ensure_ext(self.filepath, ".mdl")
        dir_path = dirname(self.filepath)
        base_name = splitext(basename(self.filepath))[0]

        # Generate a log file containing info about the data
        if GENERATE_LOG_FILE:
            LogFileWriter(dir_path, base_name).write_log()

        # Generate the MDL file
        self.export_mdl(mesh_objects, dir_path, base_name)
        
        # Generate the C file
        CFileWriter(dir_path, base_name).write_c_file()

        # Generate the texture files
        if self._model_has_textures(mesh_objects):
            TextureFileWriter(dir_path, base_name).write_texture_data()

        return {'FINISHED'}

    def invoke(self, context, event):
        # Open the file-dialog to set the export path
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def export_mdl(self, mesh_objects, dir_path, base_name):
        # Create the MDL file
        mdl_path = join(dir_path, base_name + ".mdl")
        with open(mdl_path, 'w') as mdl_file:
            mdl_file.write("/* Model Name: %s */\n" % base_name)
            mdl_file.write("/* Total Objects: %d */\n" % len(mesh_objects))
            mdl_file.write("/*\n")
            for obj in mesh_objects:
                mdl_file.write("    -%s\n" % self._safe_name(obj.name))
            mdl_file.write("*/\n\n")
            mdl_file.write('#include "sgl.h"\n')

            # Add includes and texture defs
            if self._model_has_textures(mesh_objects):
                tex_def = ''.join(base_name.split()).upper() + "_TEXTURE_NUMBER"
                mdl_file.write("#define %s 0\n\n" % tex_def)
            else:
                mdl_file.write("\n")

            # Write the data for each mesh object in the heiracy
            for obj in mesh_objects:
                try:
                    self._write_model_data(mdl_file, obj, base_name)
                except Exception as e:
                    print("Error processing {%s}" % e)

    def _model_has_textures(self, mesh_objects):
        # Check if a mesh object has a texture linked to the UV map
        for obj in mesh_objects:
            if obj.data.uv_textures.active:
                for poly in obj.data.polygons:
                    if obj.data.uv_textures.active.data[poly.index].image:
                        return True
        return False

    def _write_model_data(self, mdl_file, obj, base_name):
        # Write all of the data for the mesh object
        self._write_vertices(mdl_file, obj)
        self._write_polygons(mdl_file, obj)
        self._write_attributes(mdl_file, obj, base_name)
        self._write_xpdata(mdl_file, obj)

    def _write_vertices(self, mdl_file, obj):
        # Write all of the vertices for the mesh object in an SGL POINT array
        vertices = obj.data.vertices
        mdl_file.write("POINT point_%s[%d] = {\n" % (self._safe_name(obj.name), len(vertices)))
        for vert in vertices:
            x, y, z = vert.co * 15
            mdl_file.write("   POStoFIXED(%9.6f, %9.6f, %9.6f),\n" % (x, y, z))
        mdl_file.write("};\n\n")

    def _write_polygons(self, mdl_file, obj):
        # Write all of the faces for the mesh object in an SGL POLYGON array
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

    def _write_attributes(self, mdl_file, obj, base_name):
        # Create the SGL attribute table for the mesh object
        polygons = obj.data.polygons
        tex_def = ''.join(base_name.split()).upper() + "_TEXTURE_NUMBER"

        mdl_file.write("ATTR attribute_%s[%d] = {\n" % (self._safe_name(obj.name), len(polygons)))
        for poly in polygons:
            # Initialize default color values
            r = g = b = 31
            
            # Get the active vertex color layer
            vcol = obj.data.vertex_colors.active
            
            # If vertex colors are available, process them
            if vcol:
                for l in poly.loop_indices:
                    # Convert vertex color components to integer values
                    r = int(vcol.data[l].color.r * 31)
                    g = int(vcol.data[l].color.g * 31)
                    b = int(vcol.data[l].color.b * 31)

            # Construct the RGB color string
            c_rgb_colour = "C_RGB(%d, %d, %d)" % (r, g, b)

            # If the polygon has a texture
            if obj.data.uv_textures.active and obj.data.uv_textures.active.data[poly.index].image:
                texture = "%s+%s" % (tex_def, self.texture_id)      # Texture number of the texture to be used
                spr = "sprNoflip"                                   # Display texture normally
                mode = "CL32KRGB|MESHoff"  
                self.texture_id += 1
            else:
                texture = "No_Texture"                              # No texture used
                spr = "sprPolygon"                                  # Display polygon
                mode = "MESHoff|CL_Gouraud"

            mdl_file.write("   ATTRIBUTE(Single_Plane, SORT_CEN, %s, %s, No_Gouraud, %s, %s, No_Option),\n" % (
                texture, c_rgb_colour, mode, spr
            ))

        mdl_file.write("};\n\n")

    def _write_xpdata(self, mdl_file, obj):
        # Create the SGL XPDATA for the mesh object
        obj_name = self._safe_name(obj.name)
        mdl_file.write("VECTOR vector_%s[sizeof(point_%s) / sizeof(POINT)];\n\n" % (obj_name, obj_name))
        mdl_file.write("XPDATA XPD_%s[6] = {\n" % obj_name)
        mdl_file.write("   point_%s, sizeof(point_%s)/sizeof(POINT),\n" % (obj_name, obj_name))
        mdl_file.write("   polygon_%s, sizeof(polygon_%s)/sizeof(POLYGON),\n" % (obj_name, obj_name))
        mdl_file.write("   attribute_%s,\n" % obj_name)
        mdl_file.write("   vector_%s,\n" % obj_name)
        mdl_file.write("};\n\n")


class CFileWriter(BaseExporter):
    def __init__(self, dir_path, base_name):
        self.dir_path = dir_path
        self.base_name = base_name

    def write_c_file(self):
        # Create the C file to initialise and draw the model using SGL
        c_path = join(self.dir_path, self.base_name + ".c")
        with open(c_path, 'w') as c_file:
            self._write_includes(c_file)
            self._write_model_properties(c_file)
            self._write_model_draw_functions(c_file)
            self._write_main_draw_function(c_file)

    def _write_includes(self, c_file):
        c_file.write("#include \"%s.mdl\"\n\n" % self.base_name)

    def _write_model_property_declaration(self, c_file, c_name):
        # Declare the properties for the mesh object
        c_file.write("FIXED %s_pos[XYZ];\n" % c_name)
        c_file.write("ANGLE %s_ang[XYZ];\n" % c_name)
        c_file.write("FIXED %s_scl[XYZ];\n\n" % c_name)

    def _write_model_property_initialisation(self, c_file, c_name):
        # Initialise the properties for the mesh object
        c_file.write("  // Initialise %s properties\n" % c_name)
        c_file.write("  %s_ang[X] = %s_ang[Y] = %s_ang[Z] = DEGtoANG(0.0);\n" % (c_name, c_name, c_name))
        c_file.write("  %s_pos[X] = %s_pos[Y] = toFIXED(0.0);\n" % (c_name, c_name))
        c_file.write("  %s_pos[Z] = toFIXED(120.0);\n" % c_name)
        c_file.write("  %s_scl[X] = %s_scl[Y] = %s_scl[Z] = toFIXED(1.0);\n\n" % (c_name, c_name, c_name))

    def _write_model_properties(self, c_file):
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]

        # Write the properties for each model in the heiracy
        if len(mesh_objects) > 1:
            for obj in mesh_objects:
                if obj.parent is None:
                    continue

                c_name = self._safe_name(''.join(obj.name.split()).lower())
                c_file.write("// %s model Properties\n" % c_name.capitalize())
                self._write_model_property_declaration(c_file, c_name)

        # Write the properties for the root model
        c_name = self._safe_name(''.join(self.base_name.split()).lower())

        c_file.write("// %s model Properties (root model)\n" % c_name.capitalize())
        self._write_model_property_declaration(c_file, c_name)

        # Write the model initialise function
        c_file.write("void %s_Initialise() {\n" % c_name.capitalize())

        # Set the initial properties for each mesh object in the heiracy
        if len(mesh_objects) > 1:
            for obj in mesh_objects:
                if obj.parent is None:
                    continue

                c_name = self._safe_name(''.join(obj.name.split()).lower())
                self._write_model_property_initialisation(c_file, c_name)

        # Set the initial properties for the root object
        c_name = self._safe_name(''.join(self.base_name.split()).lower())
        self._write_model_property_initialisation(c_file, c_name)

        c_file.write("}\n\n")

    def _write_transformations(self, c_file, c_name):
        # Write the polygon transformations for the mesh object
        c_file.write("{\n")
        c_file.write("   slPushMatrix();\n")
        c_file.write("   {\n")
        c_file.write("       slTranslate(%s_pos[X], %s_pos[Y], %s_pos[Z]);\n" % (c_name, c_name, c_name))
        c_file.write("       slScale(%s_scl[X], %s_scl[Y], %s_scl[Z]);\n" % (c_name, c_name, c_name))
        c_file.write("       slRotX(%s_ang[X]);\n" % c_name)
        c_file.write("       slRotY(%s_ang[Y]);\n" % c_name)
        c_file.write("       slRotZ(%s_ang[Z]);\n\n" % c_name)
        
    def _write_model_draw_functions(self, c_file):
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        if len(mesh_objects) > 1:
            
            # Write the draw function for each mesh object in the heiracy
            for obj in mesh_objects:
                if obj.parent is None:
                    continue
                
                c_name = self._safe_name(''.join(obj.name.split()).lower())
                c_file.write("void %s_Draw(FIXED *light)\n" % c_name.capitalize())
                self._write_transformations(c_file, c_name)
                c_file.write("       // Draw the object's polygons\n")
                c_file.write("       slPutPolygonX(&XPD_%s, light);\n" % self._safe_name(obj.name))
                c_file.write("   }\n")
                c_file.write("   slPopMatrix();\n")
                c_file.write("}\n\n")

    def _write_main_draw_function(self, c_file):
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        if self.base_name:
            c_name = self._safe_name(''.join(self.base_name.split()).lower())
            c_file.write("void %s_Draw(FIXED *light)\n" % c_name.capitalize())
            
            # Write the transformations for the root object
            self._write_transformations(c_file, c_name)
            
            # Put-polygon function for the root object
            c_file.write("       // Draw the root polygon\n")
            c_file.write("       slPutPolygonX(&XPD_%s, light);\n\n" % self._safe_name(c_name.capitalize()))
            
            # Add the draw function calls for each mesh object in the heiracy
            if len(mesh_objects) > 1:
                c_file.write("       // Draw the additional polygons\n")
                for obj in mesh_objects:
                    if obj.parent is None:
                        continue
                    obj_c_name = self._safe_name(''.join(obj.name.split()).lower())
                    c_file.write("       %s_Draw(light);\n" % obj_c_name.capitalize())
            
            # Pop the root object matrix
            c_file.write("   }\n")
            c_file.write("   slPopMatrix();\n")
            c_file.write("}\n\n")


        
        
        
class TextureFileWriter(BaseExporter):
    def __init__(self, dir_path, base_name):
        self.dir_path = dir_path
        self.base_name = base_name

    def write_texture_data(self):
        # Write the texture data in a format supported by SGL
        with self._initialize_texture_file() as txr_file:
            colour_palette = set()
            texture_data = []
            tex_table = []
            pic_table = []
            texture_presize = 0
            texture_id = 0

            # Loop through all of the mesh objects that have textures applied
            for obj in bpy.data.objects:
                if obj.type == "MESH" and obj.data.uv_textures.active is not None:

                    obj_texture_number = 0

                    # Setup temporary materials and textures
                    mat, sprite_image, sprite_tex = self._setup_temp_material_and_texture(obj.name)

                    # Setup UV map and materials
                    sprite_uv = self._setup_uv_and_material(obj, mat, sprite_tex)

                    # Bake textures for the current object
                    new_tex_table, new_pic_table, new_colours, new_texture_data, obj_texture_number, texture_id, texture_presize = self._bake_sprites(obj, sprite_uv, sprite_image, sprite_tex, obj_texture_number, texture_id, texture_presize, mat)

                    # Add baked colours to the palette
                    colour_palette.update(new_colours)
                    
                    # Extend the texture data
                    texture_data.extend(new_texture_data)
                    
                    # Add the data to the texture table
                    tex_table.extend(new_tex_table)
                    
                    # Add the data to the picture table
                    pic_table.extend(new_pic_table)

                    # Cleanup the temporary uv, material and texture\image
                    self._cleanup(obj, mat, sprite_uv, sprite_image, sprite_tex)

            # Write the includes
            self._write_includes(txr_file)

            # Write the colour palette
            self._write_colour_palette(txr_file, colour_palette)

            # Write the texture data
            self._write_texture_data(txr_file, texture_data)

            # Write the texture-table
            self._write_texture_table(txr_file, tex_table)

            # Write the picture-table
            self._write_picture_table(txr_file, pic_table)

            # Write the set-texture function
            self._write_set_texture_function(txr_file)

    def _initialize_texture_file(self):
        texture_path = join(self.dir_path, self.base_name + "_texture.c")
        return open(texture_path, 'w')
        
    def _setup_temp_material_and_texture(self, obj_name):
        # Setup temporary materials and textures with unique identifiers
        mat = bpy.data.materials.new("_tmp_%s" % obj_name)
        sprite_image = bpy.data.images.new("_tmp_%s" % obj_name, 32, 32)
        sprite_tex = bpy.data.textures.new("_tmp_%s" % obj_name, type="IMAGE")
        return mat, sprite_image, sprite_tex
    
    def _cleanup(self, obj, mat, sprite_uv, sprite_image, sprite_tex):
        # Ensure the object is active and selected
        bpy.context.scene.objects.active = obj
        obj.select = True

        # Clear the texture slot in the material
        if mat.texture_slots[0] is not None:
            mat.texture_slots.clear(0)
        
        # Remove the temporary UV map
        uv_textures = obj.data.uv_textures
        for i, uv in enumerate(uv_textures):
            if uv.name == sprite_uv.name:
                uv_textures.remove(uv)
                break

        # Remove the temporary material from the object
        if obj.data.materials:
            for i, material in enumerate(obj.data.materials):
                if material == mat:
                    obj.data.materials.pop(index=i)
                    break

        # Clear references to the texture and image
        sprite_tex.image = None

        # Remove the temporary images and textures
        if sprite_image:
            sprite_image.user_clear()
            bpy.data.images.remove(sprite_image)

        if sprite_tex:
            bpy.data.textures.remove(sprite_tex)

        # Remove the temporary material
        if mat:
            bpy.data.materials.remove(mat, do_unlink=True)

    def _setup_uv_and_material(self, obj, mat, sprite_tex):
        # Ensure the correct context
        bpy.context.scene.objects.active = obj  # Set the active object in the scene to the current object
        obj.select = True  # Select the current object

        # Create a temporary UV texture layer for the object
        sprite_uv = obj.data.uv_textures.new(name="_tmp_%s" % obj.name)

        # Clear any existing images from the newly created UV texture
        for tf in obj.data.uv_textures[sprite_uv.name].data:
            tf.image = None  # Remove the image from each UV face in the UV texture layer

        # Set the newly created UV texture as the active UV map
        obj.data.uv_textures[sprite_uv.name].active = True

        # Enter Edit mode to modify the UV map
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')  # Select all faces in the mesh
        bpy.ops.uv.reset()  # Reset the UV map to a default state
        bpy.ops.mesh.select_all(action='DESELECT')  # Deselect all faces in the mesh
        bpy.ops.object.mode_set(mode='OBJECT')  # Return to Object mode

        # Add the temporary material to the mesh object
        obj.data.materials.append(mat)

        # Configure the material settings
        mat.diffuse_color = (1, 1, 1)  # Set the diffuse color to white
        mat.diffuse_intensity = 1.0  # Set the diffuse intensity to maximum
        mat.use_shadeless = True  # Disable shading for the material

        # Ensure the texture slot is initialized and configure it
        if mat.texture_slots[0] is None:
            mat.texture_slots.add()  # Add a texture slot if none exists
        mat.texture_slots[0].texture = sprite_tex  # Assign the sprite texture to the first texture slot
        mat.texture_slots[0].texture_coords = 'UV'  # Use UV coordinates for the texture
        mat.texture_slots[0].uv_layer = obj.data.uv_textures[0].name  # Set the UV layer for the texture

        # Configure the texture settings
        sprite_tex.filter_type = "BOX"  # Set the texture filter type to BOX
        sprite_tex.filter_size = 0.1  # Set the texture filter size
        sprite_tex.use_interpolation = False  # Disable interpolation for the texture
        sprite_tex.use_mipmap = False  # Disable mipmapping for the texture

        return sprite_uv  # Return the newly created UV texture layer

    def _bake_sprites(self, obj, sprite_uv, sprite_image, sprite_tex, obj_texture_number, texture_id, texture_presize, mat):
        # Initialize lists to store texture information
        tex_table = []
        pic_table = []
        texture_data = []
        color_palette = set()

        # Set up the bake type to bake textures
        bpy.context.scene.render.bake_type = 'TEXTURE'
        
        # Set the current object as the active object
        bpy.context.scene.objects.active = obj
        
        # Assign the temporary material to the object for baking
        obj.data.materials.append(mat)

        # Iterate over each UV face in the object's UV texture
        for count, uv_face in enumerate(obj.data.uv_textures[0].data):
            if uv_face.image is not None:
                # Assign the bake target image to the UV face
                obj.data.uv_textures[sprite_uv.name].data[count].image = sprite_image
                sprite_tex.image = uv_face.image

                # Perform the bake operation
                bpy.ops.object.bake_image()

                # Start writing the texture data
                texture_data.append("TEXDAT %s_tex%d[] = {\n" % (self._safe_name(obj.name), texture_id))

                # Get the pixel data from the baked image
                pixels = list(sprite_image.pixels)

                # Convert the RGBA values to 16-bit RGB565 and collect unique colors
                for x in range(0, len(pixels), 4):
                    r = int(pixels[x] * 31)
                    g = int(pixels[x + 1] * 31)
                    b = int(pixels[x + 2] * 31)
                    color = (b << 10) | (g << 5) | (r) | 0x8000  # Convert to RGB565 format
                    color_palette.add(color)

                    # Write the color value to the texture data array
                    if (x // 4) % 8 == 0:
                        texture_data.append("   %s," % hex(color))
                    elif (x // 4) % 8 == 7:
                        texture_data.append("%s,\n" % hex(color))
                    else:
                        texture_data.append("%s," % hex(color))

                # Check if the palette size exceeds 256 colors
                if len(color_palette) > 256:
                    color_palette = set(list(color_palette)[:256])

                # Add the texture definition to the texture table
                tex_table.append("   TEXDEF(%3d, %3d, %9d),\n" % (
                    sprite_image.size[0],
                    sprite_image.size[1],
                    texture_presize
                ))
                
                # Increment the previously registered texture size
                texture_presize += (sprite_image.size[0] * sprite_image.size[1])

                # Add the picture definition to the picture table
                pic_table.append("   PICDEF(%3d, COL_32K, %s_tex%d),\n" % (
                    texture_id,
                    self._safe_name(obj.name),
                    texture_id,
                ))

                # Increment the texture ID
                texture_id += 1

                # Close the texture data array
                texture_data.append("};\n\n")

                # Clear the baked image from the UV face
                obj.data.uv_textures[sprite_uv.name].data[count].image = None

        return tex_table, pic_table, color_palette, texture_data, obj_texture_number, texture_id, texture_presize

    def _write_includes(self, txr_file):
        txr_file.write('#include "sgl.h"\n')
        txr_file.write('#include "sega_sys.h"\n\n')

    def _write_colour_palette(self, txr_file, colour_palette):
        # Create the colour palette that can be loaded into VRAM
        if len(colour_palette) > 0:
            txr_file.write("// Number of Colours: %d\n" % len(colour_palette))
            palette_str = ""
            sorted_palette = sorted(colour_palette)
            for i in range(0, len(sorted_palette), 8):
                row = sorted_palette[i:i+8]
                palette_str += "   " + ",".join(hex(color) for color in row) + ",\n"
            txr_file.write("short int global_palette[] = {\n%s};\n\n" % palette_str)

    def _write_texture_data(self, txr_file, texture_data):
        # Write the texture data for all objects
        if len(texture_data) > 0:
            txr_file.write("// Texture data\n")
            for tex_data in texture_data:
                txr_file.write(tex_data)

    def _write_texture_table(self, txr_file, tex_table):
        # Create the texture-table for SGL
        if len(tex_table) > 0:
            txr_file.write("// Number of Textures: %d\n" % len(tex_table))
            txr_file.write("TEXTURE tex_table[]={\n")
            for texture in tex_table:
                txr_file.write(texture)
            txr_file.write("};\n\n")

    def _write_picture_table(self, txr_file, pic_table):
        # Create the picture-table for SGL
        if len(pic_table) > 0:
            txr_file.write("// Number of Pictures: %d\n" % len(pic_table))
            txr_file.write("PICTURE pic_table[]={\n")
            for picture in pic_table:
                txr_file.write(picture)
            txr_file.write("};\n\n")

    def _write_set_texture_function(self, txr_file):
        txr_file.write("void Set_Texture(PICTURE *pcptr , Uint32 NbPicture)\n")
        txr_file.write("{\n")
        txr_file.write("    TEXTURE *txptr;\n\n")
        txr_file.write("    for(; NbPicture-- > 0; pcptr++){\n")
        txr_file.write("        txptr = tex_table + pcptr->texno;\n")
        txr_file.write("        slDMACopy((void *)pcptr->pcsrc,\n")
        txr_file.write("            (void *)(SpriteVRAM + ((txptr->CGadr) << 3)),\n")
        txr_file.write("            (Uint32)((txptr->Hsize * txptr->Vsize * 4) >> (pcptr->cmode)));\n")
        txr_file.write("    }\n")
        txr_file.write("}\n\n")


class LogFileWriter:
    def __init__(self, dir_path, base_name):
        self.dir_path = dir_path
        self.base_name = base_name

    def write_log(self):
        # Create a log file for debugging issues with the export script/data
        log_path = join(self.dir_path, "log.txt")
        with open(log_path, 'w') as log_file:
            mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
            log_file.write("Number of Mesh objects: %d\n" % len(mesh_objects))
            for obj in mesh_objects:
                log_file.write("\nObject name: %s\n" % obj.name)
  
                if obj.parent is None:
                    log_file.write("Object does NOT have parent\n")
                else:
                    log_file.write("Object has parent\n")
                    
                # Log mesh object information
                mesh = obj.data
                log_file.write("Number of vertices: %d\n" % len(mesh.vertices))
                log_file.write("Number of edges: %d\n" % len(mesh.edges))
                log_file.write("Number of polygons: %d\n" % len(mesh.polygons))
                log_file.write("Number of materials: %d\n" % len(obj.material_slots))

                # Log material information
                for mat_slot in obj.material_slots:
                    if mat_slot.material:
                        log_file.write("Material: %s\n" % mat_slot.material.name)
                        log_file.write("Material diffuse color: %s\n" % str(mat_slot.material.diffuse_color))
                    else:
                        log_file.write("Material slot is empty\n")
                
                # Log texture information
                if mesh.uv_textures.active:
                    log_file.write("UV Textures are active\n")
                    for uv_tex in mesh.uv_textures:
                        log_file.write("UV Texture: %s\n" % uv_tex.name)
                        
                    for poly in mesh.polygons:
                        uv_layer = mesh.uv_textures.active.data
                        if uv_layer[poly.index].image:
                            log_file.write("Polygon %d has texture: %s\n" % (poly.index, uv_layer[poly.index].image.name))
                        else:
                            log_file.write("Polygon %d has no texture\n" % poly.index)
                else:
                    log_file.write("No active UV Textures\n")


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
