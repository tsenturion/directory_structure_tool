from directory_structure_tool.archives import (
    add_rar_candidates,
    ensure_directory_target,
    extract_archive_to_report_folder,
    extract_rar_to_dir,
    extract_zip_to_dir,
    find_latest_archive,
    find_rar_extractor,
    format_archive_download_time,
    get_existing_archive_result_dir,
    get_winrar_registry_paths,
    list_archive_member_parts,
    list_rar_member_parts,
    list_zip_member_parts,
    make_unique_directory_path,
    make_unique_file_path,
    merge_directory_contents,
    normalize_archive_member_parts,
    resolve_archive_path,
)
from directory_structure_tool.cli import main
from directory_structure_tool.cli import resolve_start_path
from directory_structure_tool.clipboard import copy_text_to_clipboard
from directory_structure_tool.config import (
    ARCHIVE_EXTENSIONS,
    BINARY_CHECK_BYTES,
    DOWNLOADS_DIR,
    IGNORED_DIRS,
    IGNORED_FILES,
    IGNORED_FILE_EXTENSIONS,
    NAMES_ONLY_DIRS,
    OUTPUT_FILENAME,
    SCRIPT_DIR,
    STATE_FILE,
    TEXT_ENCODINGS,
)
from directory_structure_tool.paths import (
    clean_user_input,
    format_elapsed_ago,
    is_subpath,
    pluralize_ru,
    sanitize_text_for_report,
    vscode_name_key,
)
from directory_structure_tool.repositories import (
    RepositoryReference,
    build_repository_cache_key,
    build_sourcecraft_clone_url,
    is_repository_reference,
    parse_http_repository_url,
    parse_repository_reference,
    parse_scp_like_repository_url,
    parse_transport_repository_url,
    redact_url_secrets,
    resolve_repository_path,
)
from directory_structure_tool.report import (
    save_directory_structure,
    save_file_content,
    should_skip_file_content,
)
from directory_structure_tool.state import (
    archive_cache_key,
    get_archive_signature,
    get_cached_archive_result,
    get_last_report_path,
    load_state,
    remember_archive_result,
    save_state,
)

if __name__ == "__main__":
    main()
