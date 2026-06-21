import json
import os

from .config import STATE_FILE


def load_state(state_file=STATE_FILE):
    """Загружает состояние прошлых запусков."""
    try:
        with open(state_file, "r", encoding="utf-8") as state_file_obj:
            state = json.load(state_file_obj)
        if isinstance(state, dict):
            return state
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_state(state, state_file=STATE_FILE):
    """Сохраняет состояние прошлых запусков."""
    with open(state_file, "w", encoding="utf-8") as state_file_obj:
        json.dump(state, state_file_obj, ensure_ascii=False, indent=2)


def archive_cache_key(archive_path):
    """Ключ архива для состояния, независимый от регистра пути Windows."""
    return os.path.abspath(archive_path).casefold()


def get_archive_signature(archive_path):
    """Возвращает признаки архива, по которым видно, менялся ли файл."""
    archive_stat = os.stat(archive_path)
    return {
        "path": os.path.abspath(archive_path),
        "size": archive_stat.st_size,
        "mtime_ns": archive_stat.st_mtime_ns,
    }


def get_cached_archive_result(state, archive_path):
    """Возвращает прошлую распакованную папку, если архив не менялся."""
    try:
        signature = get_archive_signature(archive_path)
    except OSError:
        return None

    archive_info = state.get("archives", {}).get(archive_cache_key(archive_path))
    if not isinstance(archive_info, dict):
        return None

    result_dir = archive_info.get("result_dir")
    if (
        archive_info.get("size") == signature["size"]
        and archive_info.get("mtime_ns") == signature["mtime_ns"]
        and result_dir
        and os.path.isdir(result_dir)
    ):
        return result_dir

    return None


def remember_archive_result(state, archive_path, result_dir):
    """Запоминает, куда был распакован конкретный архив."""
    signature = get_archive_signature(archive_path)
    signature["result_dir"] = os.path.abspath(result_dir)
    state.setdefault("archives", {})[archive_cache_key(archive_path)] = signature
    state["last_archive_path"] = signature["path"]
    state["last_archive_result_dir"] = signature["result_dir"]


def get_last_report_path(state):
    """Возвращает последний путь, по которому успешно строился отчет."""
    last_path = state.get("last_report_path")
    if last_path and os.path.isdir(last_path):
        return last_path
    return None
