# Directory Structure Tool

Утилита для генерации текстового отчета по структуре папки или архива.

```bat
python directory_structure.py
```

или:

```bat
python -m directory_structure_tool
```

## Структура

- `directory_structure.py` - совместимая точка запуска.
- `directory_structure_tool/` - пакет с логикой утилиты.
- `tests/` - базовые unit-тесты без внешних зависимостей.

## Проверка

```bat
python -m unittest discover
```
