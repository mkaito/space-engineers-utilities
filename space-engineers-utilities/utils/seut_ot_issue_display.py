import bpy
import os
import time
import subprocess

from bpy.types              import Operator
from bpy.props              import StringProperty, IntProperty

from ..seut_errors      import log, seut_report
from ..seut_utils       import wrap_text, get_preferences


class SEUT_OT_IssueDisplay(Operator):
    """Displays a list of the last 10 notifications originating from SEUT"""
    bl_idname = "wm.issue_display"
    bl_label = "SEUT Notifications"
    bl_options = {'REGISTER', 'UNDO'}


    issues_sorted = []


    def execute(self, context):

        wm = context.window_manager
        
        SEUT_OT_IssueDisplay.issues_sorted.clear()
        SEUT_OT_IssueDisplay.issues_sorted = sorted(wm.seut.issues, key=lambda issue: issue.timestamp, reverse=True)
        
        wm.seut.issue_alert = False
        
        return context.window_manager.invoke_popup(self, width=600)


    def draw(self, context):

        wm = context.window_manager
        layout = self.layout

        layout.label(text="SEUT Notifications", icon='INFO')

        if len(SEUT_OT_IssueDisplay.issues_sorted) < 1:
            layout.separator(factor=1.0)
            layout.label(text="SEUT has not generated any notifications so far.")
        else:
            split = layout.split(factor=0.75)
            split.label(text="This list displays the last 50 notifications generated by SEUT.")
            split.operator('wm.clear_issues', icon='REMOVE')
            row = layout.row()
            split = row.split(factor=0.6)
            split.operator('wm.export_log', icon='TEXT')
            split = row.split(factor=0.8)
            split.label(text="")
            split.prop(wm.seut, 'display_errors', icon='CANCEL', text="")
            split.prop(wm.seut, 'display_warnings', icon='ERROR', text="")
            split.prop(wm.seut, 'display_infos', icon='INFO', text="")
            layout.separator(factor=1.0)
        
        for issue in SEUT_OT_IssueDisplay.issues_sorted:

            index = SEUT_OT_IssueDisplay.issues_sorted.index(issue)

            if issue.issue_type == 'ERROR' and not wm.seut.display_errors:
                continue
            if issue.issue_type == 'WARNING' and not wm.seut.display_warnings:
                continue
            if issue.issue_type == 'INFO' and not wm.seut.display_infos:
                continue

            box = layout.box()

            split = box.split(factor=0.025)
            row = split.row()
            if issue.issue_type == 'ERROR':
                row.alert = True
            elif issue.issue_type == 'INFO':
                row.active = False
            row.label(text=str(index + 1))
                
            split = split.split(factor=0.70)
            row = split.row()
            if issue.issue_type == 'INFO':
                row.active = False

            if issue.issue_type == 'ERROR':
                row.alert = True
                icon = 'CANCEL'
            elif issue.issue_type == 'WARNING':
                icon = 'ERROR'
            else:
                icon = 'INFO'
            row.label(text=issue.issue_type, icon=icon)
            row.label(text=issue.code)
            row.label(text=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(issue.timestamp)))

            col = box.column()
            if issue.issue_type == 'ERROR':
                col.alert = True
                
            for text in wrap_text(issue.text, 110):
                row = col.row()
                row.scale_y = 0.75
                if issue.issue_type == 'INFO':
                    row.active = False
                row.label(text=text)

            split = split.split(factor=0.85)
            row = split.row()
            if issue.issue_type == 'ERROR':
                row.alert = True
            if issue.issue_type == 'ERROR' or issue.issue_type == 'WARNING':
                semref = row.operator('wm.semref_link', text="How to Fix", icon='INFO')
                semref.section = 'tools'
                semref.page = '4260391/Troubleshooting'
                semref.code = '#' + issue.code
                
            op = split.operator('wm.delete_issue', icon='REMOVE', text="", emboss=False)
            op.idx = index
        
        layout.separator(factor=1.0)
        split = layout.split(factor=0.75)
        split.label(text="Should no relevant error be listed here, please check the Blender System Console:")
        split.operator('wm.console_toggle', icon='CONSOLE')
        
        if len(SEUT_OT_IssueDisplay.issues_sorted) < 1:
            split = layout.split(factor=0.75)
            split.label(text="")
            split.operator('wm.export_log', icon='TEXT')


class SEUT_OT_DeleteIssue(Operator):
    """Delete specific issue"""
    bl_idname = "wm.delete_issue"
    bl_label = "Delete Issue"
    bl_options = {'REGISTER', 'UNDO'}


    idx: IntProperty()


    def execute(self, context):
        
        wm = context.window_manager

        for index in range(0, len(wm.seut.issues)):
            if wm.seut.issues[index] == SEUT_OT_IssueDisplay.issues_sorted[self.idx]:
                wm.seut.issues.remove(index)
                break

        SEUT_OT_IssueDisplay.issues_sorted.clear()
        SEUT_OT_IssueDisplay.issues_sorted = sorted(wm.seut.issues, key=lambda issue: issue.timestamp, reverse=True)
        
        return {'FINISHED'}


class SEUT_OT_ClearIssues(Operator):
    """Clears all current issues"""
    bl_idname = "wm.clear_issues"
    bl_label = "Clear Notifications"
    bl_options = {'REGISTER', 'UNDO'}


    def execute(self, context):
        
        wm = context.window_manager
        wm.seut.issues.clear()
        SEUT_OT_IssueDisplay.issues_sorted.clear()
        
        return {'FINISHED'}


class SEUT_OT_ExportLog(Operator):
    """Exports the log for this BLEND file"""
    bl_idname = "wm.export_log"
    bl_label = "Export SEUT Logs"
    bl_options = {'REGISTER', 'UNDO'}


    @classmethod
    def poll(cls, context):
        if not bpy.data.is_saved:
            Operator.poll_message_set("BLEND file must be saved before logs can be exported.")
            return False
        else:
            return True


    def execute(self, context):

        wm = context.window_manager
        scene = context.scene
        preferences = get_preferences()
        
        path = f"{os.path.splitext(bpy.data.filepath)[0]}_{time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())}.log"
        
        info = [
            f"----------------------------------------------------------------",
            f"Time:\t\t{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
            f"Blender:\t{bpy.app.version_string}",
            f"SEUT:\t\t{wm.seut.repos['space-engineers-utilities'].current_version}",
            f"----------------------------------------------------------------",
            f"Game Dir:\t{preferences.game_path}",
            f"Assets:\t\t{wm.seut.repos['seut-assets'].current_version}\t Path: {preferences.asset_path}",
            f"MWMB:\t\t{wm.seut.repos['MWMBuilder'].current_version}\t Path: {preferences.mwmb_path}",
            f"Havok Path:\t{preferences.havok_path}",
            f"----------------------------------------------------------------",
            f"BLEND Path:\t\t{bpy.data.filepath}",
            f"Icon Path:\t\t{scene.render.filepath}",
            f"Mod Path:\t\t{scene.seut.mod_path}",
            f"Export Path:\t{scene.seut.export_exportPath}",
            f"----------------------------------------------------------------\n"
        ]
        
        with open(path, "w") as f:
            for l in info:
                print(l, file=f)
            print(log.getvalue(), file=f)

        subprocess.Popen(f'explorer /select,"{path}"')

        seut_report(self, context, 'INFO', False, 'I022', path)
        
        return {'FINISHED'}