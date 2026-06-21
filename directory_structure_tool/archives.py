import os
import shutil
import subprocess
import time
import zipfile
from datetime import datetime

from .config import ARCHIVE_EXTENSIONS, DOWNLOADS_DIR
from .paths import format_elapsed_ago, is_subpath
from .state import get_cached_archive_result, remember_archive_result


def format_archive_download_time(archive_path):
    """Возвращает дату архива и сколько времени прошло с последнего изменения."""
    modified_at = os.path.getmtime(archive_path)
    modified_text = datetime.fromtimestamp(modified_at).strftime("%d.%m.%Y %H:%M:%S")
    elapsed_text = format_elapsed_ago(time.time() - modified_at)
    return f"{modified_text}, {elapsed_text}"


def find_latest_archive(downloads_dir=DOWNLOADS_DIR):
    """Возвращает самый новый zip/rar архив из папки загрузок."""
    if not os.path.isdir(downloads_dir):
        return None

    archive_paths = []
    with os.scandir(downloads_dir) as entries:
        for entry in entries:
            _, ext = os.path.splitext(entry.name)
            if entry.is_file() and ext.casefold() in ARCHIVE_EXTENSIONS:
                archive_paths.append(entry.path)

    if not archive_paths:
        return None
    return max(archive_paths, key=lambda path: (os.path.getmtime(path), os.path.getctime(path)))


def make_unique_directory_path(base_dir, preferred_name):
    """Подбирает имя папки без конфликта с существующим файлом или папкой."""
    candidate = os.path.join(base_dir, preferred_name)
    if not os.path.exists(candidate):
        return candidate

    for index in range(1, 1000):
        candidate = os.path.join(base_dir, f"{preferred_name}_{index}")
        if not os.path.exists(candidate):
            return candidate

    raise RuntimeError(f"Не удалось подобрать свободное имя папки для: {preferred_name}")


def make_unique_file_path(base_dir, preferred_name):
    """Подбирает имя файла без конфликта, сохраняя расширение."""
    name, ext = os.path.splitext(preferred_name)
    candidate = os.path.join(base_dir, preferred_name)
    if not os.path.exists(candidate):
        return candidate

    for index in range(1, 1000):
        candidate = os.path.join(base_dir, f"{name}_{index}{ext}")
        if not os.path.exists(candidate):
            return candidate

    raise RuntimeError(f"Не удалось подобрать свободное имя файла для: {preferred_name}")


def ensure_directory_target(path):
    """Создает папку назначения; если на ее месте файл, выбирает свободное имя."""
    if os.path.isdir(path):
        return path
    if os.path.exists(path):
        path = make_unique_directory_path(os.path.dirname(path), os.path.basename(path))
    os.makedirs(path, exist_ok=True)
    return path


def normalize_archive_member_parts(name):
    """Преобразует имя из архива в безопасные части относительного пути."""
    name = name.replace("\\", "/")
    if "\x00" in name:
        return None

    parts = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or ":" in part:
            return None
        parts.append(part)
    return parts


def extract_zip_to_dir(archive_path, target_dir):
    """Безопасно распаковывает zip в указанную папку."""
    target_abs = os.path.abspath(target_dir)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            parts = normalize_archive_member_parts(member.filename)
            if not parts:
                continue

            target_path = os.path.abspath(os.path.join(target_abs, *parts))
            if not is_subpath(target_path, target_abs):
                raise RuntimeError(f"Небезопасный путь внутри архива: {member.filename}")

            if member.is_dir():
                os.makedirs(target_path, exist_ok=True)
                continue

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with archive.open(member) as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)


def list_zip_member_parts(archive_path):
    """Возвращает безопасные пути zip-элементов и признак папки."""
    members = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            parts = normalize_archive_member_parts(member.filename)
            if parts:
                members.append((parts, member.is_dir()))
    return members


def get_winrar_registry_paths():
    """Ищет пути WinRAR/UnRAR в реестре Windows."""
    if os.name != "nt":
        return []

    try:
        import winreg
    except ImportError:
        return []

    paths = []
    key_names = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\UnRAR.exe",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe",
    )
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)

    for root in roots:
        for key_name in key_names:
            try:
                with winreg.OpenKey(root, key_name) as key:
                    for value_name in ("", "Path"):
                        try:
                            value, _ = winreg.QueryValueEx(key, value_name)
                        except FileNotFoundError:
                            continue
                        if value:
                            paths.append(value)
            except FileNotFoundError:
                continue

    return paths


def add_rar_candidates(candidates, path):
    """Добавляет exe-файлы WinRAR из папки или рядом с найденным exe."""
    if not path:
        return

    path = os.path.abspath(path)
    base_dir = path if os.path.isdir(path) else os.path.dirname(path)
    for exe_name in ("UnRAR.exe", "Rar.exe", "WinRAR.exe"):
        candidates.append(os.path.join(base_dir, exe_name))
    if os.path.isfile(path):
        candidates.append(path)


def find_rar_extractor():
    """Находит консольный распаковщик rar, предпочитая UnRAR."""
    candidates = []

    for exe_name in ("UnRAR.exe", "unrar.exe", "Rar.exe", "rar.exe", "WinRAR.exe", "winrar.exe"):
        found = shutil.which(exe_name)
        if found:
            candidates.append(found)

    for registry_path in get_winrar_registry_paths():
        add_rar_candidates(candidates, registry_path)

    for common_dir in (
        r"C:\Program Files\WinRAR",
        r"C:\Program Files (x86)\WinRAR",
    ):
        add_rar_candidates(candidates, common_dir)

    seen = set()
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(candidate):
            return candidate

    return None


def extract_rar_to_dir(archive_path, target_dir):
    """Распаковывает rar через UnRAR/WinRAR."""
    extractor = find_rar_extractor()
    if not extractor:
        raise RuntimeError("Для .rar не найден UnRAR.exe или WinRAR.exe.")

    exe_name = os.path.basename(extractor).casefold()
    command = [extractor, "x", "-o+", "-y"]
    if exe_name == "winrar.exe":
        command.insert(2, "-ibck")
    command.extend([archive_path, target_dir + os.sep])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        if output:
            output = output.splitlines()[-1]
        raise RuntimeError(f"Ошибка распаковки rar: {output or f'код {result.returncode}'}")


def list_rar_member_parts(archive_path):
    """Возвращает безопасные пути rar-элементов через UnRAR."""
    extractor = find_rar_extractor()
    if not extractor:
        return []
    if os.path.basename(extractor).casefold() == "winrar.exe":
        return []

    result = subprocess.run(
        [extractor, "lb", archive_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60
    )
    if result.returncode != 0:
        return []

    members = []
    for line in result.stdout.splitlines():
        parts = normalize_archive_member_parts(line)
        if parts:
            members.append((parts, False))
    return members


def list_archive_member_parts(archive_path):
    """Возвращает безопасные пути элементов архива."""
    _, ext = os.path.splitext(archive_path)
    ext = ext.casefold()
    if ext == ".zip":
        return list_zip_member_parts(archive_path)
    if ext == ".rar":
        return list_rar_member_parts(archive_path)
    return []


def get_existing_archive_result_dir(archive_path):
    """Находит уже существующую папку, в которую должен распаковаться архив."""
    archive_path = os.path.abspath(archive_path)
    downloads_dir = os.path.dirname(archive_path)
    archive_stem = os.path.splitext(os.path.basename(archive_path))[0]

    try:
        members = list_archive_member_parts(archive_path)
    except (OSError, zipfile.BadZipFile):
        members = []

    top_names = {parts[0] for parts, _ in members if parts}
    if len(top_names) == 1:
        top_name = next(iter(top_names))
        has_root_dir = any(len(parts) > 1 or is_dir for parts, is_dir in members)
        candidate = os.path.join(downloads_dir, top_name if has_root_dir else archive_stem)
    else:
        candidate = os.path.join(downloads_dir, archive_stem)

    if os.path.isdir(candidate):
        return candidate
    return None


def merge_directory_contents(source_dir, target_dir):
    """Переносит содержимое source_dir в target_dir, сливая существующие папки."""
    os.makedirs(target_dir, exist_ok=True)

    for entry in os.listdir(source_dir):
        source_path = os.path.join(source_dir, entry)
        target_path = os.path.join(target_dir, entry)

        if os.path.isdir(source_path):
            if os.path.isdir(target_path):
                merge_directory_contents(source_path, target_path)
                os.rmdir(source_path)
            else:
                if os.path.exists(target_path):
                    target_path = make_unique_directory_path(target_dir, entry)
                shutil.move(source_path, target_path)
            continue

        if os.path.isdir(target_path):
            target_path = make_unique_file_path(target_dir, entry)
            shutil.move(source_path, target_path)
        elif os.path.exists(target_path):
            try:
                os.replace(source_path, target_path)
            except PermissionError:
                target_path = make_unique_file_path(target_dir, entry)
                shutil.move(source_path, target_path)
        else:
            shutil.move(source_path, target_path)


def extract_archive_to_report_folder(archive_path):
    """Распаковывает архив так, чтобы итоговая папка не имела лишнего вложенного уровня."""
    archive_path = os.path.abspath(archive_path)
    downloads_dir = os.path.dirname(archive_path)
    archive_name = os.path.basename(archive_path)
    archive_stem, archive_ext = os.path.splitext(archive_name)
    archive_ext = archive_ext.casefold()

    if archive_ext not in ARCHIVE_EXTENSIONS:
        raise RuntimeError(f"Неподдерживаемый тип архива: {archive_ext}")

    staging_dir = make_unique_directory_path(
        downloads_dir,
        f"__directory_structure_extract_{archive_stem}"
    )
    os.makedirs(staging_dir, exist_ok=False)

    try:
        if archive_ext == ".zip":
            extract_zip_to_dir(archive_path, staging_dir)
        else:
            extract_rar_to_dir(archive_path, staging_dir)

        top_entries = os.listdir(staging_dir)
        if len(top_entries) == 1 and os.path.isdir(os.path.join(staging_dir, top_entries[0])):
            root_dir_name = top_entries[0]
            source_dir = os.path.join(staging_dir, root_dir_name)
            result_dir = ensure_directory_target(os.path.join(downloads_dir, root_dir_name))
            print(f"В архиве найдена корневая папка: {root_dir_name}")
            merge_directory_contents(source_dir, result_dir)
        else:
            result_dir = ensure_directory_target(os.path.join(downloads_dir, archive_stem))
            merge_directory_contents(staging_dir, result_dir)

        return result_dir
    finally:
        if os.path.isdir(staging_dir) and is_subpath(staging_dir, downloads_dir):
            shutil.rmtree(staging_dir)


def resolve_archive_path(archive_path, state):
    """Возвращает папку архива, распаковывая только при отсутствии актуального кеша."""
    cached_dir = get_cached_archive_result(state, archive_path)
    if cached_dir:
        print(f"Архив уже распаковывался, использую папку: {cached_dir}")
        return cached_dir

    existing_dir = get_existing_archive_result_dir(archive_path)
    if existing_dir:
        remember_archive_result(state, archive_path, existing_dir)
        print(f"Архив уже распакован, использую папку: {existing_dir}")
        return existing_dir

    print(f"Распаковываю архив: {os.path.basename(archive_path)}")
    result_dir = extract_archive_to_report_folder(archive_path)
    remember_archive_result(state, archive_path, result_dir)
    print(f"Архив распакован в папку: {result_dir}")
    return result_dir
