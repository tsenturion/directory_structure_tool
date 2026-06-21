import os

from .archives import (
    find_latest_archive,
    format_archive_download_time,
    resolve_archive_path,
)
from .clipboard import copy_text_to_clipboard
from .config import ARCHIVE_EXTENSIONS, DOWNLOADS_DIR, NAMES_ONLY_DIRS, OUTPUT_FILENAME
from .paths import clean_user_input, sanitize_text_for_report
from .repositories import is_repository_reference, resolve_repository_path
from .report import save_directory_structure
from .state import get_cached_archive_result, get_last_report_path, load_state, save_state


def resolve_start_path(raw_path, latest_archive, state):
    """Возвращает папку для отчета; Enter значит последний архив, 3 значит прошлый путь."""
    raw_path = clean_user_input(raw_path)
    if raw_path == "3":
        last_path = get_last_report_path(state)
        if not last_path:
            raise RuntimeError("Нет сохраненного прошлого пути или папка была удалена.")
        print(f"Повторяю последний путь: {last_path}")
        return last_path

    if raw_path:
        if is_repository_reference(raw_path):
            return resolve_repository_path(raw_path)
        _, ext = os.path.splitext(raw_path)
        if os.path.isfile(raw_path) and ext.casefold() in ARCHIVE_EXTENSIONS:
            return resolve_archive_path(raw_path, state)
        return raw_path

    if not latest_archive:
        return ""

    return resolve_archive_path(latest_archive, state)


def get_names_only_dirs(start_path):
    names_only_dirs = []
    for names_only_input in sorted(NAMES_ONLY_DIRS):
        if os.path.isabs(names_only_input):
            names_only_dir = os.path.abspath(names_only_input)
        else:
            names_only_dir = os.path.abspath(os.path.join(start_path, names_only_input))
        if not os.path.isdir(names_only_dir):
            continue
        names_only_dirs.append(names_only_dir)
    return names_only_dirs


def write_report(start_path, output_filename, names_only_dirs, names_only_mode):
    with open(output_filename, 'w', encoding='utf-8') as output_file:
        output_file.write(f"Структура папки: {start_path}\n\n")
        if names_only_mode:
            output_file.write("Режим: только названия файлов, без содержимого\n\n")
        if names_only_dirs:
            output_file.write("Без содержимого файлов для папок:\n")
            for p in names_only_dirs:
                output_file.write(f"- {p}\n")
            output_file.write("\n")
        save_directory_structure(
            start_path,
            output_file,
            names_only_dirs=names_only_dirs,
            names_only_mode=names_only_mode
        )


def sanitize_report_file(output_filename):
    with open(output_filename, 'r', encoding='utf-8') as result_file:
        raw_result_text = result_file.read()

    result_text = sanitize_text_for_report(raw_result_text)
    if result_text != raw_result_text:
        with open(output_filename, 'w', encoding='utf-8') as result_file:
            result_file.write(result_text)
    return result_text


def main():
    state = load_state()
    latest_archive = find_latest_archive()
    if latest_archive:
        archive_time = format_archive_download_time(latest_archive)
        print(f"\nПоследний архив в загрузках: {os.path.basename(latest_archive)} ({archive_time})")
        cached_archive_dir = get_cached_archive_result(state, latest_archive)
        if cached_archive_dir:
            print(f"Для него уже есть распакованная папка: {cached_archive_dir}")
    else:
        print(f"\nВ {DOWNLOADS_DIR} не найдено .zip/.rar архивов.")

    last_report_path = get_last_report_path(state)
    if last_report_path:
        print(f"Последний рабочий путь для режима 3: {last_report_path}")

    first_input = input(
        "\nВведите путь к папке/архиву, URL git-репозитория, '2' для режима только названий, '3' для прошлого пути или Enter для последнего архива: "
    )
    first_input = clean_user_input(first_input)
    names_only_mode = first_input == "2"

    try:
        if names_only_mode:
            second_input = input(
                "\nВведите путь к папке/архиву, URL git-репозитория, '3' для прошлого пути или Enter для последнего архива: "
            )
            start_path = resolve_start_path(second_input, latest_archive, state)
        else:
            start_path = resolve_start_path(first_input, latest_archive, state)
    except RuntimeError as e:
        print(f"Ошибка: {e}")
        start_path = ""

    if not start_path:
        print("Путь не задан.")
    elif not os.path.isdir(start_path):
        print(f"Указанный путь не является папкой: {start_path}")
    else:
        names_only_dirs = get_names_only_dirs(start_path)
        output_filename = OUTPUT_FILENAME.strip() or "directory_structure.txt"
        write_report(start_path, output_filename, names_only_dirs, names_only_mode)

        print(f"Структура папки сохранена в файл: {output_filename}")
        result_text = sanitize_report_file(output_filename)
        line_count = len(result_text.splitlines())
        print(f"Количество строк в итоговом файле: {line_count}")

        if copy_text_to_clipboard(result_text):
            print("Содержимое итогового файла скопировано в буфер обмена.")
        else:
            print("Не удалось скопировать содержимое файла в буфер обмена.")

        state["last_report_path"] = os.path.abspath(start_path)
        save_state(state)
