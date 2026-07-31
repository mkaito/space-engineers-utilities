import os
import importlib.util

_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'space-engineers-utilities', 'utils', 'seut_paths.py',
)
_spec = importlib.util.spec_from_file_location('seut_paths', _MODULE_PATH)
seut_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seut_paths)

relative_from_folder = seut_paths.relative_from_folder
to_content_path = seut_paths.to_content_path


def test_relative_from_folder_midpath_unix():
    assert relative_from_folder('/home/u/MyMod/Models/Cubes/x.fbx', 'Models', '/') == 'Models/Cubes/x.fbx'


def test_relative_from_folder_midpath_windows():
    assert relative_from_folder('C:\\m\\Models\\Cubes\\x.fbx', 'Models', '\\') == 'Models\\Cubes\\x.fbx'


def test_relative_from_folder_at_end_unix():
    assert relative_from_folder('/home/u/Models', 'Models', '/') == 'Models'


def test_relative_from_folder_at_end_windows():
    assert relative_from_folder('C:\\a\\Models', 'Models', '\\') == 'Models'


def test_relative_from_folder_absent():
    assert relative_from_folder('/home/u/foo/bar', 'Models', '/') is False


def test_relative_from_folder_multiple_occurrence():
    assert relative_from_folder('/a/Models/b/Models/c.fbx', 'Models', '/') == 'Models/c.fbx'


def test_relative_from_folder_substring_no_false_match():
    assert relative_from_folder('/a/Models/x.fbx', 'Model', '/') is False


def test_to_content_path_from_unix():
    assert to_content_path('Models/Cubes/x.mwm', '/') == 'Models\\Cubes\\x.mwm'


def test_to_content_path_from_windows_noop():
    assert to_content_path('Models\\Cubes\\x.mwm', '\\') == 'Models\\Cubes\\x.mwm'


def test_to_content_path_default_sep():
    assert to_content_path(os.sep.join(['a', 'b', 'c'])) == 'a\\b\\c'
