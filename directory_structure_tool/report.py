import io
import os

from pathspec import GitIgnoreSpec

from .config import (
    BINARY_CHECK_BYTES,
    IGNORED_DIRS,
    IGNORED_FILE_EXTENSIONS,
    IGNORED_FILES,
    NAMES_ONLY_DIRS,
    RESPECT_GITIGNORE,
    TEXT_ENCODINGS,
)
from .paths import is_subpath, sanitize_text_for_report, vscode_name_key


def resolve_names_only_dirs(start_path, names_only_dirs=None):
    resolved_dirs = []
    configured_dirs = NAMES_ONLY_DIRS if names_only_dirs is None else names_only_dirs
    for names_only_input in sorted(configured_dirs):
        if os.path.isabs(names_only_input):
            names_only_dir = os.path.abspath(names_only_input)
        else:
            names_only_dir = os.path.abspath(os.path.join(start_path, names_only_input))
        if os.path.isdir(names_only_dir):
            resolved_dirs.append(names_only_dir)
    return resolved_dirs


def write_report_content(output_file, start_path, names_only_dirs=None, names_only_mode=False):
    save_directory_structure(
        start_path,
        output_file,
        names_only_dirs=names_only_dirs,
        names_only_mode=names_only_mode,
    )


def build_report_text(start_path, names_only_dirs=None, names_only_mode=False):
    output = io.StringIO()
    write_report_content(output, start_path, names_only_dirs, names_only_mode)
    return sanitize_text_for_report(output.getvalue())


def write_report_file(start_path, output_filename, names_only_dirs=None, names_only_mode=False):
    with open(output_filename, 'w', encoding='utf-8') as output_file:
        write_report_content(output_file, start_path, names_only_dirs, names_only_mode)


def should_skip_file_content(file_path):
    """Оставляет файл в структуре, но не читает служебное/binary-содержимое."""
    path_parts = set(os.path.normpath(file_path).split(os.sep))
    file_name = os.path.basename(file_path)
    if "__MACOSX" in path_parts or file_name.startswith("._"):
        return True

    try:
        with open(file_path, "rb") as file:
            sample = file.read(BINARY_CHECK_BYTES)
    except OSError:
        return False

    if not sample:
        return False
    if b"\x00" in sample:
        return True

    control_bytes = sum(
        1
        for byte in sample
        if byte < 32 and byte not in (9, 10, 13)
    )
    return control_bytes / len(sample) > 0.2


def load_gitignore_spec(directory):
    gitignore_path = os.path.join(directory, ".gitignore")
    try:
        with open(gitignore_path, "r", encoding="utf-8-sig", errors="replace") as gitignore_file:
            return GitIgnoreSpec.from_lines(gitignore_file)
    except (OSError, UnicodeError):
        return None


def find_git_root(path):
    current_path = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current_path, ".git")):
            return current_path
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:
            return None
        current_path = parent_path


def load_initial_gitignore_specs(root_path):
    root_path = os.path.abspath(root_path)
    git_root = find_git_root(root_path)
    first_path = git_root or root_path
    relative_parts = os.path.relpath(root_path, first_path).split(os.sep)
    directories = [first_path]
    for part in relative_parts:
        if part != os.curdir:
            directories.append(os.path.join(directories[-1], part))

    gitignore_specs = []
    for directory in directories:
        spec = load_gitignore_spec(directory)
        if spec is not None:
            gitignore_specs.append((directory, spec))
    return gitignore_specs


def is_gitignored(path, is_dir, gitignore_specs):
    ignored = False
    for base_path, spec in gitignore_specs:
        try:
            relative_path = os.path.relpath(path, base_path)
        except ValueError:
            continue
        if relative_path == os.pardir or relative_path.startswith(os.pardir + os.sep):
            continue

        git_path = relative_path.replace(os.sep, "/")
        if is_dir:
            git_path += "/"
        result = spec.check_file(git_path)
        if result.include is not None:
            ignored = result.include
    return ignored


def save_directory_structure(
    root_path,
    output_file,
    indent=0,
    names_only_dirs=None,
    names_only_mode=False,
    _gitignore_specs=None,
):
    """Рекурсивно сохраняет структуру каталога и содержимое допустимых файлов."""
    if RESPECT_GITIGNORE:
        if _gitignore_specs is None:
            gitignore_specs = load_initial_gitignore_specs(root_path)
        else:
            gitignore_specs = list(_gitignore_specs)
            gitignore_spec = load_gitignore_spec(root_path)
            if gitignore_spec is not None:
                gitignore_specs.append((os.path.abspath(root_path), gitignore_spec))
    else:
        gitignore_specs = []

    try:
        entries = list(os.scandir(root_path))
    except PermissionError:
        output_file.write(" " * indent + f"[Ошибка доступа]: {root_path}\n")
        return
    except FileNotFoundError:
        output_file.write(" " * indent + f"[Папка не найдена]: {root_path}\n")
        return

    dir_entries = []
    file_entries = []

    for entry in entries:
        if entry.is_dir():
            if entry.name in IGNORED_DIRS:
                continue
            if RESPECT_GITIGNORE and is_gitignored(entry.path, True, gitignore_specs):
                continue
            dir_entries.append(entry.name)

        elif entry.is_file():
            _, ext = os.path.splitext(entry.name)
            if ext in IGNORED_FILE_EXTENSIONS or entry.name in IGNORED_FILES:
                continue
            if RESPECT_GITIGNORE and is_gitignored(entry.path, False, gitignore_specs):
                continue
            file_entries.append(entry.name)

    for entry in sorted(dir_entries, key=vscode_name_key):
        full_path = os.path.join(root_path, entry)
        output_file.write(" " * indent + f"[Папка] {entry}/\n")
        save_directory_structure(
            full_path,
            output_file,
            indent + 4,
            names_only_dirs,
            names_only_mode,
            gitignore_specs,
        )

    for entry in sorted(file_entries, key=vscode_name_key):
        full_path = os.path.join(root_path, entry)
        output_file.write(" " * indent + f"- {entry}\n")
        if names_only_mode:
            continue
        if names_only_dirs and any(is_subpath(full_path, names_only_dir) for names_only_dir in names_only_dirs):
            continue
        save_file_content(full_path, output_file, indent + 4)


def save_file_content(file_path, output_file, indent=0):
    """Сохраняет содержимое файла с отступом."""
    if should_skip_file_content(file_path):
        return

    output_file.write(" " * indent + f"[Содержимое файла: {os.path.basename(file_path)}]\n")
    last_error = None
    try:
        for encoding in TEXT_ENCODINGS:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    for line in f:
                        clean_line = sanitize_text_for_report(line.rstrip())
                        output_file.write(" " * indent + clean_line + "\n")
                return
            except UnicodeDecodeError as e:
                last_error = e
                continue
        if last_error:
            output_file.write(" " * indent + f"[Ошибка чтения файла: {last_error}]\n")
    except Exception as e:
        output_file.write(" " * indent + f"[Ошибка чтения файла: {e}]\n")
