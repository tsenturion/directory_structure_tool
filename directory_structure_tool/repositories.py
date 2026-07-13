import hashlib
import os
import re
import shutil
from dataclasses import dataclass, replace
from urllib.parse import ParseResult, quote, unquote, urlparse, urlunparse

from .config import REPOSITORY_CACHE_DIR
from .subprocess_utils import run_hidden


KNOWN_REPOSITORY_HOSTS = {
    "github.com": "GitHub",
    "gitlab.com": "GitLab",
    "gitverse.ru": "GitVerse",
    "gitflic.ru": "GitFlic",
    "sourcecraft.dev": "SourceCraft",
    "git.sourcecraft.dev": "SourceCraft",
}
SOURCECRAFT_WEB_HOST = "sourcecraft.dev"
SOURCECRAFT_GIT_HOST = "git.sourcecraft.dev"
WEB_PATH_MARKERS = {"-", "tree", "blob", "src", "commit", "commits", "branches", "merge_requests", "pulls"}
SCP_LIKE_GIT_URL_RE = re.compile(r"^(?P<user>[^@\s]+)@(?P<host>[^:\s]+):(?P<path>.+)$")
WINDOWS_INVALID_NAME_CHARS_RE = re.compile(r'[<>:"\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class RepositoryReference:
    provider: str
    clone_url: str
    display_name: str
    cache_key: str
    ref: str = ""
    subpath: str = ""
    subpath_kind: str = ""


def normalize_host(host):
    host = (host or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    return host


def strip_git_suffix(name):
    if name.casefold().endswith(".git"):
        return name[:-4]
    return name


def split_repo_path(path):
    return [unquote(part) for part in path.split("/") if part]


def trim_web_path(parts):
    trimmed = []
    for part in parts:
        if part in WEB_PATH_MARKERS:
            break
        trimmed.append(part)
    return trimmed


def normalize_repository_subpath(parts):
    safe_parts = []
    for part in parts:
        if part in ("", ".", "..") or ":" in part:
            return ""
        safe_parts.append(part)
    return "/".join(safe_parts)


def parse_web_ref_and_subpath(parts):
    if not parts:
        return "", "", ""
    marker = parts[0]
    if marker not in {"tree", "blob", "src"} or len(parts) < 2:
        return "", "", ""
    ref = parts[1]
    subpath = normalize_repository_subpath(parts[2:])
    subpath_kind = "file" if marker == "blob" and subpath else "directory"
    return ref, subpath, subpath_kind


def split_http_repository_parts_with_kind(parsed, host):
    parts = split_repo_path(parsed.path)
    if not parts:
        return [], "", "", ""

    if host == "gitlab.com" and "-" in parts:
        marker_index = parts.index("-")
        repo_parts = parts[:marker_index]
        ref, subpath, subpath_kind = parse_web_ref_and_subpath(parts[marker_index + 1:])
        return repo_parts, ref, subpath, subpath_kind

    if host in {"github.com", "gitverse.ru"} and len(parts) >= 2:
        repo_parts = parts[:2]
        ref, subpath, subpath_kind = parse_web_ref_and_subpath(parts[2:])
        return repo_parts, ref, subpath, subpath_kind

    if host == SOURCECRAFT_WEB_HOST and len(parts) >= 2:
        repo_parts = parts[:2]
        ref, subpath, subpath_kind = parse_web_ref_and_subpath(parts[2:])
        return repo_parts, ref, subpath, subpath_kind

    if host == "gitflic.ru":
        if parts[0] == "project" and len(parts) >= 3:
            repo_parts = parts[:3]
            ref, subpath, subpath_kind = parse_web_ref_and_subpath(parts[3:])
            return repo_parts, ref, subpath, subpath_kind
        if len(parts) >= 2:
            repo_parts = ["project", *parts[:2]]
            ref, subpath, subpath_kind = parse_web_ref_and_subpath(parts[2:])
            return repo_parts, ref, subpath, subpath_kind

    return trim_web_path(parts), "", "", ""


def split_http_repository_parts(parsed, host):
    repo_parts, ref, subpath, _ = split_http_repository_parts_with_kind(parsed, host)
    return repo_parts, ref, subpath


def get_provider_for_host(host, path_parts):
    if host in KNOWN_REPOSITORY_HOSTS:
        return KNOWN_REPOSITORY_HOSTS[host]
    if path_parts and path_parts[-1].casefold().endswith(".git"):
        return "Git"
    return None


def build_https_url(parsed, host, repo_parts):
    path = "/" + "/".join(quote(part.strip("/")) for part in repo_parts)
    if not path.casefold().endswith(".git"):
        path += ".git"

    netloc = parsed.netloc
    if normalize_host(parsed.hostname) != host:
        netloc = host

    return urlunparse(
        ParseResult(
            scheme=parsed.scheme,
            netloc=netloc,
            path=path,
            params="",
            query="",
            fragment="",
        )
    )


def build_sourcecraft_clone_url(repo_parts):
    path = "/".join(quote(part.strip("/")) for part in repo_parts)
    if not path.casefold().endswith(".git"):
        path += ".git"
    return f"https://git@{SOURCECRAFT_GIT_HOST}/{path}"


def get_repo_parts_from_url(parsed, host):
    parts, _, _ = split_http_repository_parts(parsed, host)
    return parts


def parse_http_repository_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = normalize_host(parsed.hostname)
    parts, ref, subpath, subpath_kind = split_http_repository_parts_with_kind(parsed, host)
    provider = get_provider_for_host(host, parts)
    if not provider or not parts:
        return None

    if host == SOURCECRAFT_WEB_HOST:
        clone_url = build_sourcecraft_clone_url(parts)
    else:
        clone_host = SOURCECRAFT_GIT_HOST if host == SOURCECRAFT_GIT_HOST else host
        clone_url = build_https_url(parsed, clone_host, parts)

    display_name = strip_git_suffix(parts[-1])
    return RepositoryReference(
        provider=provider,
        clone_url=clone_url,
        display_name=display_name,
        cache_key=build_repository_cache_key(provider, clone_url, display_name, ref=ref, subpath=subpath),
        ref=ref,
        subpath=subpath,
        subpath_kind=subpath_kind,
    )


def parse_transport_repository_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"ssh", "git"}:
        return None

    host = normalize_host(parsed.hostname)
    path_parts = split_repo_path(parsed.path)
    provider = get_provider_for_host(host, path_parts)
    if not provider or not path_parts:
        return None

    display_name = strip_git_suffix(path_parts[-1])
    return RepositoryReference(
        provider=provider,
        clone_url=value,
        display_name=display_name,
        cache_key=build_repository_cache_key(provider, value, display_name),
    )


def parse_scp_like_repository_url(value):
    match = SCP_LIKE_GIT_URL_RE.match(value)
    if not match:
        return None

    host = normalize_host(match.group("host"))
    path_parts = split_repo_path(match.group("path"))
    provider = get_provider_for_host(host, path_parts)
    if not provider or not path_parts:
        return None

    display_name = strip_git_suffix(path_parts[-1])
    return RepositoryReference(
        provider=provider,
        clone_url=value,
        display_name=display_name,
        cache_key=build_repository_cache_key(provider, value, display_name),
    )


def parse_repository_reference(value):
    """Распознает URL удаленного git-репозитория для поддерживаемых хостингов."""
    value = value.strip()
    return (
        parse_scp_like_repository_url(value)
        or parse_transport_repository_url(value)
        or parse_http_repository_url(value)
    )


def is_repository_reference(value):
    """Проверяет, похож ли ввод на поддерживаемый URL удаленного git-репозитория."""
    return parse_repository_reference(value) is not None


def redact_url_secrets(text):
    """Убирает токены из URL перед выводом ошибок."""
    return re.sub(r"(https?://)([^/@\s]+)@", r"\1***@", text)


def build_repository_cache_key(provider, clone_url, display_name, ref="", subpath=""):
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", display_name).strip("._-") or "repository"
    hash_source = "\n".join([
        redact_url_secrets(clone_url).casefold(),
        ref.casefold(),
        subpath.casefold(),
    ])
    url_hash = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()[:12]
    return f"{provider.casefold()}_{safe_name}_{url_hash}"


def run_git(command, cwd=None, timeout=300):
    result = run_hidden(
        ["git", *command],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(redact_url_secrets(output or f"git завершился с кодом {result.returncode}"))
    return result.stdout.strip()


def ensure_git_available():
    if not shutil.which("git"):
        raise RuntimeError("Для работы с удаленными репозиториями нужен установленный git.")


def list_remote_heads(clone_url):
    """Возвращает имена веток удаленного репозитория."""
    try:
        output = run_git(["ls-remote", "--heads", clone_url], timeout=300)
    except RuntimeError:
        return set()

    heads = set()
    prefix = "refs/heads/"
    for line in output.splitlines():
        _, separator, remote_ref = line.partition("\t")
        if separator and remote_ref.startswith(prefix):
            heads.add(remote_ref[len(prefix):])
    return heads


def resolve_remote_reference(reference):
    """Уточняет границу между веткой с '/' и путем внутри репозитория."""
    if not reference.ref or not reference.subpath:
        return reference

    path_parts = [reference.ref, *reference.subpath.split("/")]
    remote_heads = list_remote_heads(reference.clone_url)
    for part_count in range(len(path_parts), 0, -1):
        candidate_ref = "/".join(path_parts[:part_count])
        if candidate_ref not in remote_heads:
            continue

        subpath = "/".join(path_parts[part_count:])
        if candidate_ref == reference.ref and subpath == reference.subpath:
            return reference
        return replace(
            reference,
            ref=candidate_ref,
            subpath=subpath,
            cache_key=build_repository_cache_key(
                reference.provider,
                reference.clone_url,
                reference.display_name,
                ref=candidate_ref,
                subpath=subpath,
            ),
        )
    return reference


def normalize_git_path_part(part):
    """Приводит часть пути Git к имени, которое можно создать в Windows."""
    normalized = WINDOWS_INVALID_NAME_CHARS_RE.sub("_", part).rstrip(" .")
    if not normalized:
        normalized = "_"

    stem = normalized.split(".", 1)[0].casefold()
    if stem in WINDOWS_RESERVED_NAMES:
        normalized = f"{normalized}_"
    return normalized


def normalize_git_path_parts(path):
    """Возвращает безопасные переносимые части пути из Git-архива."""
    if "\x00" in path or path.startswith("/"):
        return None

    parts = path.rstrip("/").split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        return None
    return [normalize_git_path_part(part) for part in parts]


def list_git_blob_entries(target_dir, subpath=""):
    command = ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"]
    if subpath:
        command.extend(["--", subpath])

    result = run_hidden(
        command,
        cwd=target_dir,
        capture_output=True,
        timeout=900,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(redact_url_secrets(output or f"git ls-tree завершился с кодом {result.returncode}"))

    entries = []
    for record in result.stdout.split(b"\x00"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        if not separator:
            continue
        fields = metadata.decode("ascii", errors="replace").split()
        if len(fields) != 3 or fields[1] != "blob":
            continue
        entries.append((raw_path.decode("utf-8", errors="replace"), fields[2]))
    return entries


def read_git_blob(target_dir, object_id):
    result = run_hidden(
        ["git", "cat-file", "blob", object_id],
        cwd=target_dir,
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(redact_url_secrets(output or f"git cat-file завершился с кодом {result.returncode}"))
    return result.stdout


def write_git_blob_to_worktree(target_dir, repository_path, content):
    """Записывает blob Git под совместимым с Windows именем без изменения содержимого."""
    normalized_parts = normalize_git_path_parts(repository_path)
    if not normalized_parts:
        return None

    target_path = os.path.join(target_dir, *normalized_parts)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    if os.path.isdir(target_path):
        shutil.rmtree(target_path)
    with open(target_path, "wb") as target:
        target.write(content)
    return target_path


def clear_repository_worktree(target_dir):
    for entry in os.scandir(target_dir):
        if entry.name == ".git":
            continue
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path)
        else:
            os.unlink(entry.path)


def materialize_repository_without_checkout(reference, target_dir):
    entries = list_git_blob_entries(target_dir, reference.subpath)
    clear_repository_worktree(target_dir)
    for repository_path, object_id in entries:
        content = read_git_blob(target_dir, object_id)
        write_git_blob_to_worktree(target_dir, repository_path, content)


def can_recover_invalid_checkout(error, target_dir):
    return (
        "invalid path" in str(error).casefold()
        and os.path.isdir(os.path.join(target_dir, ".git"))
    )


def clone_repository(reference, target_dir):
    reference = resolve_remote_reference(reference)
    command = [
        "clone",
        "--depth",
        "1",
        "--no-tags",
    ]
    if reference.subpath:
        command.extend(["--filter=blob:none", "--sparse"])
    if reference.ref:
        command.extend(["--branch", reference.ref])
    command.extend([reference.clone_url, target_dir])

    try:
        run_git(command, timeout=900)
        if reference.subpath:
            apply_sparse_checkout(reference, target_dir)
    except RuntimeError as error:
        if not can_recover_invalid_checkout(error, target_dir):
            raise
        materialize_repository_without_checkout(reference, target_dir)
    return reference


def apply_sparse_checkout(reference, target_dir):
    mode_option = "--no-cone" if reference.subpath_kind == "file" else "--cone"
    run_git(["sparse-checkout", "set", mode_option, "--", reference.subpath], cwd=target_dir, timeout=300)


def update_repository(target_dir):
    run_git(["pull", "--ff-only", "--depth", "1", "--no-tags"], cwd=target_dir, timeout=900)


def get_repository_report_path(reference, target_dir):
    if not reference.subpath:
        return target_dir
    report_path = os.path.join(target_dir, *reference.subpath.split("/"))
    if not os.path.exists(report_path):
        normalized_parts = normalize_git_path_parts(reference.subpath)
        if normalized_parts:
            report_path = os.path.join(target_dir, *normalized_parts)
    if reference.subpath_kind == "file":
        if not os.path.isfile(report_path):
            raise RuntimeError(f"Файл репозитория не найден после sparse checkout: {reference.subpath}")
        return os.path.dirname(report_path)
    if not os.path.isdir(report_path):
        raise RuntimeError(f"Папка репозитория не найдена после sparse checkout: {reference.subpath}")
    return report_path


def resolve_repository_path(raw_url):
    """Клонирует или обновляет удаленный репозиторий и возвращает локальную папку."""
    reference = parse_repository_reference(raw_url)
    if not reference:
        raise RuntimeError("URL не похож на поддерживаемый git-репозиторий.")

    ensure_git_available()
    reference = resolve_remote_reference(reference)
    os.makedirs(REPOSITORY_CACHE_DIR, exist_ok=True)
    target_dir = os.path.join(REPOSITORY_CACHE_DIR, reference.cache_key)

    if os.path.isdir(os.path.join(target_dir, ".git")):
        print(f"Обновляю репозиторий {reference.provider}: {reference.display_name}")
        update_repository(target_dir)
        if reference.subpath:
            apply_sparse_checkout(reference, target_dir)
    else:
        if os.path.exists(target_dir):
            raise RuntimeError(f"Путь кеша репозитория уже занят не git-папкой: {target_dir}")
        print(f"Клонирую репозиторий {reference.provider}: {reference.display_name}")
        clone_repository(reference, target_dir)

    return get_repository_report_path(reference, target_dir)
