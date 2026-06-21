import os

from .config import (
    BINARY_CHECK_BYTES,
    IGNORED_DIRS,
    IGNORED_FILE_EXTENSIONS,
    IGNORED_FILES,
    TEXT_ENCODINGS,
)
from .paths import is_subpath, sanitize_text_for_report, vscode_name_key


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


def save_directory_structure(root_path, output_file, indent=0, names_only_dirs=None, names_only_mode=False):
    """Рекурсивно сохраняет структуру каталога и содержимое допустимых файлов."""
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
            dir_entries.append(entry.name)

        elif entry.is_file():
            _, ext = os.path.splitext(entry.name)
            if ext in IGNORED_FILE_EXTENSIONS or entry.name in IGNORED_FILES:
                continue
            file_entries.append(entry.name)

    for entry in sorted(dir_entries, key=vscode_name_key):
        full_path = os.path.join(root_path, entry)
        output_file.write(" " * indent + f"[Папка] {entry}/\n")
        save_directory_structure(full_path, output_file, indent + 4, names_only_dirs, names_only_mode)

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
