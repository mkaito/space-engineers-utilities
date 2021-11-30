import bpy
import os
import sys
import json
import addon_utils

from bpy.types  import Operator, AddonPreferences
from bpy.props  import BoolProperty, StringProperty, EnumProperty, IntProperty

from .utils.seut_updater            import check_update
from .seut_errors                   import seut_report, get_abs_path
from .seut_utils                    import get_preferences
from .seut_bau                      import draw_bau_ui, get_config, set_config


preview_collections = {}


class SEUT_OT_SetDevPaths(Operator):
    """Sets the SEUT dev paths"""
    bl_idname = "wm.set_dev_paths"
    bl_label = "Set Dev Paths"
    bl_options = {'REGISTER', 'UNDO'}


    def execute(self, context):
        preferences = get_preferences()
        
        check_update(get_addon_version())

        # enenra
        if os.path.isdir("D:\\Modding\\Space Engineers\\SEUT\\seut-assets\\Materials\\"):
            preferences.game_path = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\SpaceEngineers\\"
            preferences.asset_path = "D:\\Modding\\Space Engineers\\SEUT\\seut-assets\\"
            preferences.mwmb_path = "D:\\Modding\\Space Engineers\\SEUT\\Tools\\StollieMWMBuilder\\MwmBuilder.exe"
            preferences.havok_path = "D:\\Modding\\Space Engineers\\SEUT\\Tools\\Havok\\HavokContentTools\\hctStandAloneFilterManager.exe"
        
        # Stollie
        elif os.path.isdir("C:\\3D_Projects\\SpaceEngineers\\MaterialLibraries\\Materials\\"):
            preferences.asset_path = "C:\\3D_Projects\\SpaceEngineers\\MaterialLibraries\\"
            preferences.mwmb_path = "C:\\3D_Projects\\BlenderPlugins\\StollieMWMBuilder\\MwmBuilder.exe"
            preferences.havok_path = "C:\\3D_Projects\\BlenderPlugins\\Havok\\HavokContentTools\\hctStandAloneFilterManager.exe"
        
        else:
            load_addon_prefs()

        return {'FINISHED'}


def update_game_path(self, context):
    scene = context.scene

    if self.game_path == "":
        return
    
    path = get_abs_path(self.game_path)

    if os.path.isdir(path):
        if not path.endswith('SpaceEngineers'):
            seut_report(self, context, 'ERROR', False, 'E012', "Game Directory", path)
            self.game_path = ""
    else:
        if os.path.basename(os.path.dirname(path)) == 'SpaceEngineers':
          self.game_path = os.path.dirname(path) + '\\'
        else:
          seut_report(self, context, 'ERROR', False, 'E003', 'SpaceEngineers', path)
          self.game_path = ""
    
    save_addon_prefs()


def update_asset_path(self, context):
    scene = context.scene

    if self.asset_path == "":
        return
    
    path = get_abs_path(self.asset_path)

    if os.path.isdir(path):
        os.makedirs(os.path.join(path, 'Materials'), exist_ok=True)
        bpy.ops.wm.refresh_matlibs()
    
    save_addon_prefs()


def update_havok_path(self, context):
    filename = 'hctStandAloneFilterManager.exe'

    if self.havok_path == "":
        return
    elif self.havok_path == self.havok_path_before:
        return

    path = get_abs_path(self.havok_path)
    
    self.havok_path_before = verify_tool_path(self, context, path, "Havok Stand Alone Filter Manager", filename)
    self.havok_path = verify_tool_path(self, context, path, "Havok Stand Alone Filter Manager", filename)

    save_addon_prefs()


def update_mwmb_path(self, context):
    name = str('MwmBuilder.exe')

    if self.mwmb_path == "":
        return
    elif self.mwmb_path == self.mwmb_path_before:
        return

    path = get_abs_path(self.mwmb_path)
    
    self.mwmb_path_before = verify_tool_path(self, context, path, "MWM Builder", name)
    self.mwmb_path = verify_tool_path(self, context, path, "MWM Builder", name)

    save_addon_prefs()


def get_addon():
    return sys.modules.get(__package__)
    

class SEUT_AddonPreferences(AddonPreferences):
    """Saves the preferences set by the user"""
    bl_idname = __package__

    dev_mode: BoolProperty(
        default = get_addon().bl_info['dev_version'] > 0
    )
    asset_path: StringProperty(
        name="Asset Directory",
        description="This directory contains all SEUT assets. It contains both a Materials- and a Textures-folder",
        subtype='DIR_PATH',
        update=update_asset_path
    )
    game_path: StringProperty(
        name="Game Directory",
        description="This is the path to the directory where Space Engineers is installed",
        subtype='DIR_PATH',
        update=update_game_path
    )
    havok_path: StringProperty(
        name="Havok Standalone Filter Manager",
        description="This tool is required to create Space Engineers collision models",
        subtype='FILE_PATH',
        update=update_havok_path
    )
    havok_path_before: StringProperty(
        subtype='FILE_PATH'
    )
    mwmb_path: StringProperty(
        name="MWM Builder",
        description="This tool converts the individual 'loose files' that the export yields into MWM files the game can read",
        subtype='FILE_PATH',
        update=update_mwmb_path
    )
    mwmb_path_before: StringProperty(
        subtype='FILE_PATH'
    )

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        addon = sys.modules.get(__package__)

        self.dev_mode = get_addon().bl_info['dev_version'] > 0

        preview_collections = get_icons()
        pcoll = preview_collections['main']

        split = layout.split(factor=0.90)
        split.label(text="")
        split = split.split(factor=0.5)
        split.operator('wm.discord_link', text="", icon_value=pcoll['discord'].icon_id)
        link = split.operator('wm.semref_link', text="", icon='INFO')
        link.section = 'reference'
        link.page = '6127826/SEUT+Preferences'

        draw_bau_ui(self, context)
        if addon_utils.check('blender_addon_updater') != (True, True):
            row = layout.row()
            row.label(text="Update Status:")

            if wm.seut.needs_update:
                row.alert = True
                row.label(text=wm.seut.update_message, icon='ERROR')
                row.operator('wm.get_update', icon='IMPORT')
            else:
                row.label(text=wm.seut.update_message, icon='CHECKMARK')
                row.operator('wm.get_update', text="Releases", icon='IMPORT')

            box = layout.box()
            box.label(text="Install the Blender Addon Updater to easily update SEUT:", icon='FILE_REFRESH')
            row = box.row()
            row.scale_y = 2.0
            op = row.operator('wm.url_open', text="Blender Addon Updater", icon='URL')
            op.url = "https://github.com/enenra/blender_addon_updater/releases/"

        if self.dev_mode:
            layout.operator('wm.set_dev_paths', icon='FILEBROWSER')

        layout.prop(self, "game_path", expand=True)

        box = layout.box()
        split = box.split(factor=0.65)
        split.label(text="Assets", icon='ASSET_MANAGER')
        split.operator('wm.mass_convert_textures', icon='FILE_REFRESH')
        box.prop(self, "asset_path", expand=True)

        box = layout.box()
        box.label(text="External Tools", icon='TOOL_SETTINGS')
        box.prop(self, "mwmb_path", expand=True)
        box.prop(self, "havok_path", expand=True)


def load_icons():
    import bpy.utils.previews
    icon_discord = bpy.utils.previews.new()
    icon_dir = os.path.join(os.path.dirname(__file__), "assets")
    icon_discord.load("discord", os.path.join(icon_dir, "discord.png"), 'IMAGE')

    preview_collections['main'] = icon_discord


def unload_icons():
    
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()


def get_icons() -> dict:
    return preview_collections


def verify_tool_path(self, context, path: str, name: str, filename: str) -> str:
    """Verifies the path of an external tool"""

    # If it's a directory but appending the name gives a valid path, do that. Else, error.
    if os.path.isdir(path):
        if os.path.exists(os.path.join(path, filename)):
            return os.path.join(path, filename)
        else:
            seut_report(self, context, 'ERROR', False, 'E030', 'directory', 'EXE')
            return ""

    # If it's not a directory and the path doesn't exist, error. If the basename is equal to the name, use the path. If the basename is not equal, error.
    elif not os.path.isdir(path):
        if not os.path.exists(path):
            seut_report(self, context, 'ERROR', False, 'E003', name, path)
            return ""
        else:
            if os.path.basename(path) == filename:
                return path
            else:
                seut_report(self, context, 'ERROR', False, 'E013', name, filename, os.path.basename(path))
                return ""


def get_addon_version():
    return addon_version


def save_addon_prefs():

    wm = bpy.context.window_manager
    path = os.path.join(bpy.utils.user_resource('CONFIG'), 'space-engineers-utilities.cfg')
    preferences = get_preferences()

    data = get_config()
    
    with open(path, 'w') as cfg_file:
        json.dump(data, cfg_file, indent = 4)

    if addon_utils.check('blender_addon_updater') == (True, True) and __package__ in wm.bau.addons:
        bpy.ops.wm.bau_save_config(name=__package__, config=str(data))


def load_addon_prefs():

    wm = bpy.context.window_manager
    if addon_utils.check('blender_addon_updater') == (True, True) and __package__ in wm.bau.addons:
        config = wm.bau.addons[__package__].config
        if config != "":
            set_config(config)

    else:
        path = os.path.join(bpy.utils.user_resource('CONFIG'), 'space-engineers-utilities.cfg')
        preferences = get_preferences()

        if os.path.exists(path):
            with open(path) as cfg_file:
                data = json.load(cfg_file)
                set_config(data)