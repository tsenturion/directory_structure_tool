# Directory Structure Tool

Утилита для генерации текстового отчета по структуре папки, архива или git-репозитория.

```bat
python directory_structure.py
```

или:

```bat
python -m directory_structure_tool
```

Поддерживаются URL репозиториев GitHub, GitLab, GitVerse, GitFlic и SourceCraft.
Для приватных репозиториев используйте уже настроенные git credentials или URL с токеном.

## Структура

- `directory_structure.py` - ручная точка запуска.
- `directory_structure_tool/` - пакет с логикой утилиты и публичным API.
- `tests/` - базовые unit-тесты без внешних зависимостей.

## Проверка

```bat
python -m unittest discover
```
