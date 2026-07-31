import os


def relative_from_folder(abspath: str, folder_name: str, sep: str = os.sep):
    """Returns abspath capped before the last occurrence of folder_name, or False if absent.

    Result keeps the given separator (os-native by default). bpy-free for testability.
    """
    offset = abspath.rfind(sep + folder_name + sep)

    if offset == -1:
        if abspath.endswith(sep + folder_name):
            return abspath[abspath.rfind(sep + folder_name) + 1:]
        return False

    return abspath[offset + 1:]


def to_content_path(rel: str, sep: str = os.sep) -> str:
    """Converts an os-native relative path to SE content form (backslash-separated)."""
    return rel.replace(sep, '\\')
