import os


IGNORED_DIRS = {
    '.git',
    'bin',
    '__pycache__',
    '.idea',
    '.pytest_cache',
    '.venv',
    'node_modules',
    'l',
    'obj',
    'dist',
    #'stages',
    #'chunking_stages',
    #'embedding_stages',
    #'agent_app',
    'rag_data_prep.egg-info',
    'data',
    #'playbooks',
    'mlruns',
}

IGNORED_FILE_EXTENSIONS = {'.user'}
IGNORED_FILES = {
    'package-lock.json',
    '.DS_Store',
    '.directory_structure_state.json',
    '00-network-check.yaml',
    'k8s_full_cleanup.yaml'
}
# При True файлы и папки, исключенные правилами .gitignore, не попадают в отчет.
RESPECT_GITIGNORE = True
#NAMES_ONLY_DIRS = {'swaggerui'}
NAMES_ONLY_DIRS = {}
# Хардкод-настройки запуска
OUTPUT_FILENAME = "directory_structure.txt"
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(PACKAGE_DIR)
STATE_FILE = os.path.join(SCRIPT_DIR, ".directory_structure_state.json")
DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
REPOSITORY_CACHE_DIR = os.path.join(SCRIPT_DIR, ".directory_structure_repos")
ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z'}
TEXT_ENCODINGS = ("utf-8-sig", "utf-16", "cp1251")
BINARY_CHECK_BYTES = 4096
