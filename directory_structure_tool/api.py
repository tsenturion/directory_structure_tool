import os
import shutil
import tempfile
from contextlib import contextmanager

from .archives import extract_archive_to_dir
from .config import ARCHIVE_EXTENSIONS
from .repositories import clone_repository, parse_repository_reference
from .report import build_report_text as _build_report_text
from .report import resolve_names_only_dirs


def get_names_only_dirs(start_path, names_only_dirs=None):
    return resolve_names_only_dirs(start_path, names_only_dirs or None)


def build_report_text(start_path, names_only_dirs=None, names_only_mode=False):
    return _build_report_text(start_path, names_only_dirs, names_only_mode)


def _select_archive_root(extract_dir):
    entries = os.listdir(extract_dir)
    if len(entries) == 1:
        only_entry = os.path.join(extract_dir, entries[0])
        if os.path.isdir(only_entry):
            return only_entry
    return extract_dir


@contextmanager
def resolved_report_source(source):
    """Resolves a folder, file, archive, or repository URL to a temporary report folder."""
    source = str(source or "").strip()
    temp_root = None
    try:
        reference = parse_repository_reference(source)
        if reference:
            temp_root = tempfile.mkdtemp(prefix="directory_structure_repo_")
            target_dir = os.path.join(temp_root, reference.display_name or "repository")
            clone_repository(reference, target_dir)
            yield target_dir
            return

        source_path = os.path.abspath(source)
        if os.path.isdir(source_path):
            yield source_path
            return

        if not os.path.isfile(source_path):
            raise RuntimeError(f"Источник не найден: {source}")

        _, ext = os.path.splitext(source_path)
        ext = ext.casefold()
        temp_root = tempfile.mkdtemp(prefix="directory_structure_source_")

        if ext in ARCHIVE_EXTENSIONS:
            extract_dir = os.path.join(temp_root, "extracted")
            os.makedirs(extract_dir, exist_ok=False)
            extract_archive_to_dir(source_path, extract_dir)
            yield _select_archive_root(extract_dir)
            return

        file_dir = os.path.join(temp_root, "submitted_file")
        os.makedirs(file_dir, exist_ok=False)
        shutil.copy2(source_path, os.path.join(file_dir, os.path.basename(source_path)))
        yield file_dir
    finally:
        if temp_root and os.path.isdir(temp_root):
            shutil.rmtree(temp_root, ignore_errors=True)


def generate_report_text(source, names_only_mode=False):
    with resolved_report_source(source) as start_path:
        names_only_dirs = get_names_only_dirs(start_path)
        return build_report_text(start_path, names_only_dirs, names_only_mode)
