import bpy
import os
import re
import math
import glob
import subprocess
import xml.etree.ElementTree as ET
import xml.dom.minidom

from os.path                                import join
from mathutils                              import Matrix	
from bpy_extras.io_utils                    import axis_conversion, ExportHelper

from ..utils.seut_tool_utils                import get_tool_dir
from ..seut_collections                     import get_collections, get_rev_ref_cols
from ..seut_utils                           import *
from ..seut_errors                          import seut_report, get_abs_path
from .seut_custom_fbx_exporter              import save_single
from .seut_export_transparent_mat           import export_transparent_mat
from .seut_export_texture                   import export_material_textures


def export_xml(self, context, collection) -> str:
    """Exports the XML definition for a collection"""

    scene = context.scene
    preferences = get_preferences()
    collections = get_collections(scene)

    # Create XML tree and add initial parameters.
    model = ET.Element('Model')
    model.set('Name', scene.seut.subtypeId)

    if scene.seut.sceneType != 'character' and scene.seut.sceneType != 'character_animation':
        add_subelement(model, 'RescaleFactor', '1.0')
        add_subelement(model, 'Centered', 'false')
        add_subelement(model, 'RescaleToLengthInMeters', 'false')
            
    elif scene.seut.sceneType == 'character' or scene.seut.sceneType == 'character_animation':
        add_subelement(model, 'RescaleFactor', '0.01')

    if scene.seut.sceneType == 'character' or scene.seut.sceneType == 'character_animation':
        add_subelement(model, 'RotationY', '180')
    
    path = get_abs_path(scene.seut.export_exportPath)

    # Write local materials as material entries into XML, write library materials as matrefs into XML
    for mat in bpy.data.materials:

        if mat == None:
            continue
        if mat.users == 0 or mat.users == 1 and mat.use_fake_user:
            continue
        # This is a legacy check to filter out the old material presets.
        if mat.name[:5] == 'SMAT_':
            continue
            
        if mat.asset_data is not None:
            if mat.asset_data.seut.is_dlc:
                seut_report(self, context, 'WARNING', False, 'W012', mat.name)

        is_unique = False
        # Case 1: linked + asset -> no entry (unless not vanilla)
        if mat.library is not None and mat.asset_data is not None:
            if not mat.asset_data.seut.is_vanilla:
                is_unique = True
        # Case 2: linked but no asset -> no entry (compatibility)
        elif mat.library is not None and mat.asset_data is None:
            continue
        # Case 3: local + asset -> entry (unless vanilla)
        elif mat.library is None and mat.asset_data is not None:
            if not mat.asset_data.seut.is_vanilla:
                is_unique = True
        # Case 4: local -> entry unless the textures are from the assets folder (with exception of Custom-folder in Textures) and thus vanilla
        elif mat.library is None and mat.asset_data is None:
            nodes = mat.node_tree.nodes
            for img_type in ['CM', 'ADD', 'NG', 'ALPHAMASK']:
                if img_type in nodes and nodes[img_type].image is not None and os.path.exists(get_abs_path(nodes[img_type].image.filepath)):
                    if not check_vanilla_texture(nodes[img_type].image.filepath):
                        is_unique = True
                        break
            
        if is_unique:
            create_mat_entry(self, context, model, mat)
            if mat.asset_data is None or (mat.asset_data is not None and not mat.asset_data.seut.is_vanilla):
                export_material_textures(self, context, mat)
            if mat.seut.technique in ['GLASS', 'HOLO', 'SHIELD'] and scene.seut.export_sbc_type in ['update', 'new']:
                export_transparent_mat(self, context, mat.name)
        else:
            matRef = ET.SubElement(model, 'MaterialRef')
            matRef.set('Name', mat.name)

    # Write LOD references into the XML, if applicable
    if collection.seut.col_type in ['main', 'bs'] and 'lod' in collections:
        if not collections['lod'] is None:
            cols = get_rev_ref_cols(collections, collection, 'lod')
            for col in cols:
                if len(col.objects) > 0:
                    create_lod_entry(model, col.seut.lod_distance, path, get_col_filename(col))
        
    # Create file with subtypename + collection name and write string to it
    xml_formatted = format_xml(self, context, model)

    path = os.path.join(path, f"{get_col_filename(collection)}.xml")
    exported_xml = open(path, "w")
    exported_xml.write(xml_formatted)

    return {'FINISHED'}


def get_col_filename(collection: object) -> str:
    """Returns the correct filename for a given collection."""

    schema = {
        'main': "{subtypeId}",
        'hkt': "{ref_col_name}",
        'bs': "{subtypeId}_BS{type_index}",
        'lod': "{ref_col_name}_LOD{type_index}" 
    }

    subtypeId = collection.seut.scene.seut.subtypeId
    type_index = collection.seut.type_index

    ref_col_name = ""
    ref_col = collection.seut.ref_col
    if ref_col is not None:
        ref_col_name = schema[ref_col.seut.col_type].format(subtypeId=subtypeId, type_index=ref_col.seut.type_index)

    return schema[collection.seut.col_type].format(subtypeId=subtypeId, type_index=type_index, ref_col_name=ref_col_name)


def add_subelement(parent, name: str, value):
    """Adds a subelement to XML definition"""
    
    param = ET.SubElement(parent, 'Parameter')
    param.set('Name', name)
    param.text = str(value)


def create_texture_entry(self, context, mat_entry, mat_name: str, images: dict, tex_type: str, tex_name: str, tex_name_long: str):
    """Creates a texture entry for a texture type into the XML tree"""
    
    rel_path = create_relative_path(images[tex_type].filepath, "Textures")
    
    if not rel_path:
        seut_report(self, context, 'ERROR', False, 'E007', tex_name, mat_name)
        return
    else:
        add_subelement(mat_entry, tex_name_long, os.path.splitext(rel_path)[0] + ".dds")
    
    if not is_valid_resolution(images[tex_type].size[0]) or not is_valid_resolution(images[tex_type].size[1]):
        seut_report(self, context, 'WARNING', True, 'W004', tex_name, mat_name, f"{images[tex_type].size[0]}x{images[tex_type].size[1]}")


def is_valid_resolution(number: int) -> bool:
    """Returns True if number is a valid resolution (a square of 2)"""
    
    if number <= 0:
        return False

    return math.log(number, 2).is_integer()


def create_mat_entry(self, context, tree, mat):
    """Creates a material entry in the given tree for a given material"""

    mat_entry = ET.SubElement(tree, 'Material')
    mat_entry.set('Name', mat.name)

    add_subelement(mat_entry, 'Technique', mat.seut.technique)

    if mat.seut.facing != 'None':
        add_subelement(mat_entry, 'Facing', mat.seut.facing)
    if mat.seut.windScale != 0:
        add_subelement(mat_entry, 'WindScale', round(mat.seut.windScale, 3))
    if mat.seut.windFrequency != 0:
        add_subelement(mat_entry, 'WindFrequency', round(mat.seut.windFrequency, 3))
    
    images = {
        'cm': None,
        'ng': None,
        'add': None,
        'am': None
        }
    if mat.node_tree is not None:
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                if node.name == 'CM':
                    images['cm'] = node.image
                if node.name == 'NG':
                    images['ng'] = node.image
                if node.name == 'ADD':
                    images['add'] = node.image
                if node.name == 'ALPHAMASK':
                    images['am'] = node.image

    if images['cm'] == None and images['ng'] == None and images['add'] == None and images['am'] == None:
        tree.remove(mat_entry)
        seut_report(self, context, 'INFO', False, 'I001', mat.name)

    else:
        if mat.seut.technique not in ['HOLO', 'GLASS']:
            if not images['cm'] == None:
                create_texture_entry(self, context, mat_entry, mat.name, images, 'cm', 'CM', 'ColorMetalTexture')
            if not images['ng'] == None:
                create_texture_entry(self, context, mat_entry, mat.name, images, 'ng', 'NG', 'NormalGlossTexture')
            if not images['add'] == None:
                create_texture_entry(self, context, mat_entry, mat.name, images, 'add', 'ADD', 'AddMapsTexture')
            if not images['am'] == None:
                create_texture_entry(self, context, mat_entry, mat.name, images, 'am', 'ALPHAMASK', 'AlphamaskTexture')


def create_lod_entry(tree, distance: int, path: str, filename: str):
    """Creates a LOD entry into the XML tree"""
    
    lod = ET.SubElement(tree, 'LOD')
    lod.set('Distance', str(distance))
    lodModel = ET.SubElement(lod, 'Model')
    lodModel.text = create_relative_path(os.path.join(path, filename), "Models")


def format_xml(self, context, tree) -> str:
    """Converts XML Tree to a formatted XML string"""

    temp_string = ET.tostring(tree, 'utf-8')

    try:
        temp_string.decode('ascii')
    except UnicodeDecodeError:
        seut_report(self, context, 'ERROR', False, 'E033')

    xml_string = xml.dom.minidom.parseString(temp_string)
    
    return xml_string.toprettyxml()


def export_fbx(self, context, collection) -> str:
    """Exports the FBX file for a defined collection"""

    scene = context.scene
    collections = get_collections(scene)
    depsgraph = context.evaluated_depsgraph_get()
    settings = ExportSettings(scene, depsgraph)

    path = get_abs_path(scene.seut.export_exportPath)
    
    # Export exports the active layer_collection so the collection's layer_collection needs to be set as the active one
    try:
        bpy.context.scene.collection.children.link(collection)
    except:
        pass
    layer_collection = bpy.context.view_layer.layer_collection.children[collection.name]
    bpy.context.view_layer.active_layer_collection = layer_collection
    
    # Prepare empties for export
    for empty in collection.objects:
        if empty is not None and empty.type == 'EMPTY':

            # This not being 1.0 can cause some issues ingame.
            empty.empty_display_size = 1.0
            
            # Remove numbers
            # To ensure they work ingame (where duplicate names are no issue) this will remove the ".001" etc. from the name (and cause another empty to get this numbering)
            if re.search("\.[0-9]{3}", empty.name[-4:]) != None and not empty.seut.linked:
                if empty.name[:-4] in bpy.data.objects:
                    temp_obj = bpy.data.objects[empty.name[:-4]]
                    temp_obj.name = empty.name + " TEMP"
                    empty.name = empty.name[:-4]
                    temp_obj.name = temp_obj.name[:-len(" TEMP")]
                else:
                    empty.name = empty.name[:-4]

            # Check parenting
            if empty.parent is None and not empty.seut.linked:
                seut_report(self, context, 'WARNING', True, 'W005', empty.name, collection.name)
            elif empty.parent.parent is not None:
                seut_report(self, context, 'WARNING', True, 'W006', empty.name, empty.parent.name, collection.name)

            # Additional parenting checks
            rescale = False
            if 'highlight' in empty:
                rescale = True
                
                if len(empty.seut.highlight_objects) > 0:

                    highlights = ""
                    for entry in empty.seut.highlight_objects:
                        if not empty is None and not entry.obj is None:
                            if empty.parent is not None and entry.obj.parent is not None and empty.parent != entry.obj.parent:
                                seut_report(self, context, 'WARNING', True, 'W007', empty.name, entry.obj.name)

                            if highlights == "":
                                highlights = entry.obj.name
                            else:
                                highlights = highlights + ';' + entry.obj.name

                    empty['highlight'] = highlights
            
            elif 'file' in empty and empty.seut.linkedScene is not None:
                linked_scene = empty.seut.linkedScene
                if linked_scene.seut.export_largeGrid != scene.seut.export_largeGrid or linked_scene.seut.export_smallGrid != scene.seut.export_smallGrid:
                    seut_report(self, context, 'WARNING', True, 'W001', linked_scene.name, scene.name)

                # Remove subpart instances
                reference = get_subpart_reference(empty, collections)
                reference = correct_for_export_type(scene, reference)
                empty['file'] = reference
                unlink_subpart_scene(empty)
            
            # Blender FBX export halves empty size on export, this works around it
            if rescale:
                empty.scale.x *= 2
                empty.scale.y *= 2
                empty.scale.z *= 2
                context.view_layer.update()

    # Prepare materials for export
    for mat in bpy.data.materials:
        if mat is not None and mat.node_tree is not None:
            prepare_mat_for_export(self, context, mat)

    # Export the collection to FBX
    path = os.path.join(path, f"{get_col_filename(collection)}.fbx")
    try:
        export_to_fbxfile(settings, scene, path, collection.objects, ishavokfbxfile=False)

    except RuntimeError as error:
        seut_report(self, context, 'ERROR', False, 'E017')

    except KeyError as error:
        seut_report(self, context, 'ERROR', True, 'E038', error)

    # Revert materials back to original form
    for mat in bpy.data.materials:
        if mat is not None and mat.node_tree is not None:
            revert_mat_after_export(self, context, mat)
    
    # Relink all subparts to empties
    for empty in collection.objects:
        if empty is not None and empty.type == 'EMPTY':
            
            if scene.seut.linkSubpartInstances:
                if 'file' in empty and empty.seut.linkedScene is not None and empty.seut.linkedScene.name in bpy.data.scenes:                    
                    reference = get_subpart_reference(empty, collections)
                        
                    link_subpart_scene(self, scene, empty, empty.users_collection[0])
                    empty['file'] = reference

            # Resetting empty size
            if 'highlight' in empty :
                empty.scale.x *= 0.5
                empty.scale.y *= 0.5
                empty.scale.z *= 0.5

    bpy.context.scene.collection.children.unlink(collection)

    return {'FINISHED'}


def get_subpart_reference(empty, collections: dict) -> str:
    """Returns the corrected subpart reference."""

    parent_collection = empty.users_collection[0]

    if parent_collection.seut.col_type == 'bs':
        for bs in collections['bs']:
            if parent_collection == bs:
                return f"{empty.seut.linkedScene.seut.subtypeId}_BS{bs.seut.type_index}" # Special case, can't use get_col_filename.

    return empty.seut.linkedScene.seut.subtypeId


def correct_for_export_type(scene, reference: str) -> str:
    """Corrects reference depending on export type (large / small) selected."""

    if scene.seut.gridScale == 'large':
        if reference.startswith("LG_") or reference.find("_LG_") != -1 or reference.endswith("_LG"):
            pass

        elif reference.startswith("SG_") or reference.find("_SG_") != -1 or reference.endswith("_SG"):
            if reference.startswith("SG_"):
                reference = reference.replace("SG_", "LG_")
            elif reference.find("_SG_") != -1:
                reference = reference.replace("_SG_", "_LG_")
            elif reference.endswith("_SG"):
                reference = reference.replace("_SG", "_LG")

        elif scene.seut.export_largeGrid and scene.seut.export_smallGrid:
            reference = "LG_" + reference

    elif scene.seut.gridScale == 'small':
        if reference.startswith("SG_") or reference.find("_SG_") != -1 or reference.endswith("_SG"):
            pass

        elif reference.startswith("LG_") or reference.find("_LG_") != -1 or reference.endswith("_LG"):
            if reference.startswith("LG_"):
                reference = reference.replace("LG_", "SG_")
            elif reference.find("_LG_") != -1:
                reference = reference.replace("_LG_", "_SG_")
            elif reference.endswith("_LG"):
                reference = reference.replace("_LG", "_SG")

        elif scene.seut.export_largeGrid and scene.seut.export_smallGrid:
            reference = "SG_" + reference

    return reference


def prepare_mat_for_export(self, context, material):
    """Switches material around so that SE can properly read it"""
    
    # See if relevant nodes already exist
    dummy_shader_node = None
    dummy_image_node = None
    dummy_image = None
    material_output = None

    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED' and node.name == 'EXPORT_DUMMY':
            dummy_shader_node = node
        elif node.type == 'TEX_IMAGE' and node.name == 'DUMMY_IMAGE':
            dummy_image_node = node
        elif node.type == 'OUTPUT_MATERIAL':
            material_output = node

    # Iterate through images to find the dummy image
    for img in bpy.data.images:
        if img.name == 'DUMMY':
            dummy_image = img

    # If it doesn't exist, create it and a DUMMY image node, and link them up
    if dummy_image_node is None:
        dummy_image_node = material.node_tree.nodes.new('ShaderNodeTexImage')
        dummy_image_node.name = 'DUMMY_IMAGE'
        dummy_image_node.label = 'DUMMY_IMAGE'

    if dummy_image is None:
        dummy_image = bpy.data.images.new('DUMMY', 1, 1)

    if dummy_shader_node is None:
        dummy_shader_node = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        dummy_shader_node.name = 'EXPORT_DUMMY'
        dummy_shader_node.label = 'EXPORT_DUMMY'
    
    if material_output is None:
        material_output = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
        material.seut.nodeLinkedToOutputName = ""

    # This allows the reestablishment of connections after the export is complete.
    else:
        try:
            material.seut.nodeLinkedToOutputName = material_output.inputs[0].links[0].from_node.name
        except IndexError:
            seut_report(self, context, 'INFO', False, 'I005', material.name)

    # link nodes, add image to node
    material.node_tree.links.new(dummy_image_node.outputs[0], dummy_shader_node.inputs[0])
    material.node_tree.links.new(dummy_shader_node.outputs[0], material_output.inputs[0])
    dummy_image_node.image = dummy_image


def revert_mat_after_export(self, context, material):
    """Removes the dummy nodes from the material again after export"""

    material_output = None
    node_linked_to_output = None

    # Remove dummy nodes - do I need to remove the links too?
    # Image can stay, it's 1x1 px so nbd
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.name == 'DUMMY_IMAGE':
            material.node_tree.nodes.remove(node)
        elif node.type == 'BSDF_PRINCIPLED' and node.name == 'EXPORT_DUMMY':
            material.node_tree.nodes.remove(node)
        elif node.type == 'OUTPUT_MATERIAL':
            material_output = node
        elif node.name == material.seut.nodeLinkedToOutputName:
            node_linked_to_output = node
    
    # link the node group back to output
    if node_linked_to_output is not None:
        try:
            material.node_tree.links.new(node_linked_to_output.outputs[0], material_output.inputs[0])
        except IndexError:
            seut_report(self, context, 'INFO', False, 'I005', material.name)


def export_collection(self, context, collection):
    """Exports the collection to XML and FBX"""

    print("\n------------------------------ Exporting Collection '" + collection.name + "'.")
    result_xml = export_xml(self, context, collection)
    result_fbx = export_fbx(self, context, collection)
    print("------------------------------ Finished exporting Collection '" + collection.name + "'.\n")

    return result_xml, result_fbx


# STOLLIE: Standard output error operator class for catching error return codes.
class StdoutOperator():
    def report(self, type, message):
        print(message)

# STOLLIE: Assigning of above class to a global constant.
STDOUT_OPERATOR = StdoutOperator()

# STOLLIE: Processes subprocesss tool error messages, e.g. FBXImporter/HavokTool/MWMBuilder.
class MissbehavingToolError(subprocess.SubprocessError):
    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        return self.message

# STOLLIE: Returns a tools path from the user preferences config, e.g. FBXImporter/HavokTool/MWMBuilder.
def tool_path(propertyName, displayName, toolPath=None):
    """Gets path to tool from user preferences.

    Returns:
    toolPath
    """
    if toolPath is None:
        # STOLLIE: This is referencing the folder name the addon is stored in.
        addon = __package__[:__package__.find(".")]
        toolPath = getattr(bpy.context.preferences.addons.get(addon).preferences, propertyName)

    if toolPath is None:
        raise FileNotFoundError("%s is not configured", (displayName))

    toolPath = os.path.abspath(bpy.path.abspath(toolPath))
    if os.path.isfile(toolPath) is None:
        raise FileNotFoundError("%s: no such file %s" % (displayName, toolPath))

    return toolPath

# STOLLIE: Called by other methods to write to a log file when an errors occur.
def write_to_log(logfile, content, cmdline=None, cwd=None, loglines=[]):
    with open(logfile, 'wb') as log: # wb params here represent writing/create file and binary mode.
        if cwd:
            str = "Running from: %s \n" % (cwd)
            log.write(str.encode('utf-8'))

        if cmdline:
            str = "Command: %s \n" % (" ".join(cmdline))
            log.write(str.encode('utf-8'))

        for line in loglines:
            log.write(line.encode('utf-8'))
            log.write(b"\n")

        log.write(content)


class ExportSettings:
    def __init__(self, scene, depsgraph, mwmDir=None):
        self.scene = scene # ObjectSource.getObjects() uses .utils.scene() instead
        self.depsgraph = depsgraph
        self.operator = STDOUT_OPERATOR
        self.isLogToolOutput = True
        
        # set on first access, see properties below
        self._fbximporter = None
        self._havokfilter = None
        self._mwmbuilder = None

        
    @property
    def fbximporter(self):
        if self._fbximporter == None:
            self._fbximporter = os.path.join(get_tool_dir(), 'FBXImporter.exe')
        return self._fbximporter

    @property
    def havokfilter(self):
        if self._havokfilter == None:
            self._havokfilter = tool_path('havok_path', 'Havok Standalone Filter Tool')
        return self._havokfilter

    @property
    def mwmbuilder(self):
        if self._mwmbuilder == None:
            self._mwmbuilder = tool_path('mwmb_path', 'MWM Builder')
        return self._mwmbuilder

    def callTool(self, context, cmdline, tooltype, logfile=None, cwd=None, successfulExitCodes=[0], loglines=[], logtextInspector=None):
        try:
            out = subprocess.check_output(cmdline, cwd=cwd, stderr=subprocess.STDOUT, shell=True)
            if self.isLogToolOutput and logfile:
                write_to_log(logfile, out, cmdline=cmdline, cwd=cwd, loglines=loglines)
            if logtextInspector is not None:
                logtextInspector(out)

            out_str = out.decode("utf-8")
            if out_str.find(": ERROR:") != -1:
                if out_str.find("Assimp.AssimpException: Error loading unmanaged library from path: Assimp32.dll") != -1:
                    seut_report(self, context, 'ERROR', False, 'E039')
                    return False
                    
                elif out_str.find("System.ArgumentOutOfRangeException: Index was out of range. Must be non-negative and less than the size of the collection.") != -1:
                    temp_string = out_str[out_str.find("\\Models\\") + len("\\Models\\"):]
                    temp_string = temp_string[:temp_string.find(".fbx")]
                    seut_report(self, context, 'ERROR', False, 'E043', temp_string + ".fbx")
                    return False
            
                else:
                    seut_report(self, context, 'ERROR', False, 'E044')
                    return False

            return True

        except subprocess.CalledProcessError as e:
            if self.isLogToolOutput and logfile:
                write_to_log(logfile, e.output, cmdline=cmdline, cwd=cwd, loglines=loglines)
            if e.returncode not in successfulExitCodes:
                if e.returncode == 4294967295:
                    seut_report(self, context, 'ERROR', False, 'E037')
                elif e.returncode == 3221225477:
                    seut_report(self, context, 'ERROR', False, 'E047')
                else:
                    seut_report(self, context, 'ERROR', False, 'E035', str(tooltype))
                raise

            return False
    
    def __getitem__(self, key): # makes all attributes available for parameter substitution
        if not type(key) is str or key.startswith('_'):
            raise KeyError(key)
        try:
            value = getattr(self, key)
            if value is None or type(value) is _FUNCTION_TYPE:
                raise KeyError(key)
            return value
        except AttributeError:
            raise KeyError(key)

# HARAG: UP = 'Y'
# HARAG: FWD = 'Z'
# HARAG: MATRIX_NORMAL = axis_conversion(to_forward=FWD, to_up=UP).to_4x4()
# HARAG: MATRIX_SCALE_DOWN = Matrix.Scale(0.2, 4) * MATRIX_NORMAL
def export_to_fbxfile(settings: ExportSettings, scene, filepath, objects, ishavokfbxfile = False, kwargs = None):	
    kwargs = {	
        
        # Operator settings
        'version': 'BIN7400',
        'path_mode': 'AUTO',
        'batch_mode': 'OFF', # STOLLIE: Part of Save method not save single in Blender source, default = OFF.	

        # Include settings.
        'object_types': {'MESH', 'EMPTY'}, # STOLLIE: Is None in Blender source.
        'use_custom_props': False, # HARAG: SE / Havok properties are hacked directly into the modified fbx importer in fbx.py

        # Transform settings.
        'global_scale': 0.1, # STOLLIE: Is 1.0 in Blender Source
        'apply_scale_options': 'FBX_SCALE_NONE',
        'axis_forward': 'Z', # STOLLIE: Normally a Y in Blender source. -Z is correct forward.
        'axis_up': 'Y',	 # STOLLIE: Normally a Z in Blender source.	Y aligns correctly in SE.
        
        # HARAG: The export to Havok needs this, it's off for the MwmFileNode (bake_space_transform).
        # STOLLIE: This is False on Blender source. If set to True on MWM exports it breaks subpart orientations (bake_space_transform).
        'bake_space_transform': False,

        # Geometry settings.
        'mesh_smooth_type': 'OFF', # STOLLIE: Normally 'FACE' in Blender source.
        'use_subsurf': False,
        'use_mesh_modifiers': True,
        'use_mesh_edges': False, # STOLLIE: True in Blender source.
        'use_tspace': False, # BLENDER: Why? Unity is expected to support tspace import...	
        'use_mesh_modifiers_render': True,

         # For amature.
        'primary_bone_axis': 'X', # STOLLIE: Swapped for SE, Y in Blender source.	
        'secondary_bone_axis': 'Y', # STOLLIE: Swapped for SE, X in Blender source.
        'armature_nodetype': 'NULL',
        'use_armature_deform_only': False,
        'add_leaf_bones': False,

        # For animations.
        'bake_anim': False, # HARAG: no animation export to SE by default - STOLLIE: True in Blender source.
        'bake_anim_use_all_bones': True,
        'bake_anim_use_nla_strips': True,
        'bake_anim_use_all_actions': True,
        'bake_anim_force_startend_keying': True,
        'bake_anim_step': 1.0,
        'bake_anim_simplify_factor': 1.0,
                
        # Random properties not seen in Blender FBX export UI.
        'ui_tab': 'SKIP_SAVE',
        'global_matrix': Matrix(),
        'use_metadata': True,
        'embed_textures': False,
        'use_anim' : False, # HARAG: No animation export to SE by default - STOLLIE: Not a Blender property.
        'use_anim_action_all' : True, # Not a Blender property.	
        'use_default_take' : True, # Not a Blender property.	
        'use_anim_optimize' : True, # Not a Blender property.	
        'anim_optimize_precision' : 6.0, # Not a Blender property.	
        'use_batch_own_dir': True,	# STOLLIE: Part of Save method not save single in Blender source, default = False.
    }	

    if kwargs:	
        if isinstance(kwargs, bpy.types.PropertyGroup):	
            kwargs = {prop : getattr(kwargs, prop) for prop in kwargs.rna_type.properties.keys()}	
        kwargs.update(**kwargs)

    # These cannot be overriden and are always set here
    kwargs['use_selection'] = False # because of context_objects
    kwargs['context_objects'] = objects	# STOLLIE: Is None in Blender Source.

    if ishavokfbxfile:
        kwargs['bake_space_transform'] = True        
    
    if scene.seut.sceneType == 'subpart':
        kwargs['axis_forward'] = '-Z'

    if scene.seut.sceneType == 'character':
        kwargs['global_scale'] = 1.00
        kwargs['axis_forward'] = '-Z'
        kwargs['object_types'] = {'MESH', 'EMPTY', 'ARMATURE'} # STOLLIE: Is None in Blender source.
        kwargs['add_leaf_bones'] = True # HARAG: No animation export to SE by default - STOLLIE: Not a Blender property.     
        kwargs['apply_unit_scale'] = True # HARAG: No animation export to SE by default - STOLLIE: Not a Blender property.    

    if scene.seut.sceneType == 'character_animation':
        kwargs['axis_forward'] = '-Z'
        kwargs['object_types'] = {'EMPTY', 'ARMATURE'} # STOLLIE: Is None in Blender source.
        kwargs['use_armature_deform_only'] = True
        kwargs['bake_anim'] = True # HARAG: no animation export to SE by default - STOLLIE: True in Blender source.
        kwargs['bake_anim_simplify_factor'] = 0.0
        kwargs['use_anim'] = True # HARAG: No animation export to SE by default - STOLLIE: Not a Blender property.
        kwargs['apply_unit_scale'] = True # HARAG: No animation export to SE by default - STOLLIE: Not a Blender property.    

    # if scene.seut.sceneType != 'character' and scene.seut.sceneType != 'character_animation':
    global_matrix = axis_conversion(to_forward=kwargs['axis_forward'], to_up=kwargs['axis_up']).to_4x4()
    scale = kwargs['global_scale']

    scale *= scene.seut.export_rescaleFactor

    if abs(1.0-scale) >= 0.000001:
        global_matrix = Matrix.Scale(scale, 4) @ global_matrix

    kwargs['global_matrix'] = global_matrix
    
    return save_single(	
        settings.operator,	
        settings.scene,	
        settings.depsgraph,	
        filepath=filepath,	
        **kwargs # Stores any number of Keyword Arguments into a dictionary called 'fbxSettings'.	
    )