import os
from .seut_ot_export        import ExportSettings

def mwmbuilder(self, context, path, settings: ExportSettings, fbxfile: str, havokfile: str, paramsfile: str, mwmfile: str, materialspath):
    try:
        scene = context.scene
        cmdline = [settings.mwmbuilder, '/f', '/s:.\\', '/o:'+path+'', '/x:'+materialspath+'']
        # cmdline = [settings.mwmbuilder, '/s:Sources', '/m:'+basename+'.fbx', '/o:.\\' , '/x:'+settings.materialref , '/lod:'+settings.lodsmwmDir]
        settings.callTool(cmdline, cwd=path, logfile=mwmfile+'.log')
    finally:
        self.report({'INFO'}, "SEUT: MWM file(s) have been created.")        