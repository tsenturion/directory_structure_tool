import os


def is_subpath(path, parent):
    """Проверяет, что path находится внутри parent."""
    try:
        path_abs = os.path.abspath(path)
        parent_abs = os.path.abspath(parent)
        return os.path.commonpath([path_abs, parent_abs]) == parent_abs
    except (ValueError, TypeError):
        return False


def vscode_name_key(name):
    """Сортировка имен в стиле VSCode: регистронезависимо."""
    return name.casefold()


def clean_user_input(value):
    """Убирает пробелы и кавычки вокруг пути, если путь вставлен из проводника."""
    return value.strip().strip('"').strip("'")


def sanitize_text_for_report(text):
    """Удаляет управляющие символы, которые ломают файл и буфер обмена."""
    clean_chars = []
    for char in text:
        code = ord(char)
        if char in ("\n", "\r", "\t"):
            clean_chars.append(char)
        elif 32 <= code < 127 or code >= 160:
            clean_chars.append(char)
    return "".join(clean_chars)


def pluralize_ru(value, one, few, many):
    """Возвращает русскую форму слова для числа."""
    last_two = value % 100
    if 11 <= last_two <= 14:
        return many

    last_digit = value % 10
    if last_digit == 1:
        return one
    if 2 <= last_digit <= 4:
        return few
    return many


def format_elapsed_ago(seconds):
    """Форматирует прошедшее время: секунды, минуты, часы или дни."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        value = seconds
        unit = pluralize_ru(value, "секунду", "секунды", "секунд")
    elif seconds < 3600:
        value = seconds // 60
        unit = pluralize_ru(value, "минуту", "минуты", "минут")
    elif seconds < 86400:
        value = seconds // 3600
        unit = pluralize_ru(value, "час", "часа", "часов")
    else:
        value = seconds // 86400
        unit = pluralize_ru(value, "день", "дня", "дней")

    return f"{value} {unit} назад"
