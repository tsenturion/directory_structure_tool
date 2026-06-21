import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from urllib.parse import ParseResult, quote, unquote, urlparse, urlunparse

from .config import REPOSITORY_CACHE_DIR


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


@dataclass(frozen=True)
class RepositoryReference:
    provider: str
    clone_url: str
    display_name: str
    cache_key: str


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
    parts = trim_web_path(split_repo_path(parsed.path))
    if not parts:
        return []

    if host == "gitflic.ru" and parts[0] != "project" and len(parts) >= 2:
        parts = ["project", *parts[:2]]
    elif host in {"github.com", "gitverse.ru"} and len(parts) >= 2:
        parts = parts[:2]
    elif host == SOURCECRAFT_WEB_HOST and len(parts) >= 2:
        parts = parts[:2]

    return parts


def parse_http_repository_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = normalize_host(parsed.hostname)
    parts = get_repo_parts_from_url(parsed, host)
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
        cache_key=build_repository_cache_key(provider, clone_url, display_name),
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


def build_repository_cache_key(provider, clone_url, display_name):
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", display_name).strip("._-") or "repository"
    url_hash = hashlib.sha256(redact_url_secrets(clone_url).casefold().encode("utf-8")).hexdigest()[:12]
    return f"{provider.casefold()}_{safe_name}_{url_hash}"


def run_git(command, cwd=None, timeout=300):
    result = subprocess.run(
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


def clone_repository(reference, target_dir):
    run_git(
        [
            "clone",
            "--depth",
            "1",
            "--no-tags",
            reference.clone_url,
            target_dir,
        ],
        timeout=900,
    )


def update_repository(target_dir):
    run_git(["pull", "--ff-only", "--depth", "1", "--no-tags"], cwd=target_dir, timeout=900)


def resolve_repository_path(raw_url):
    """Клонирует или обновляет удаленный репозиторий и возвращает локальную папку."""
    reference = parse_repository_reference(raw_url)
    if not reference:
        raise RuntimeError("URL не похож на поддерживаемый git-репозиторий.")

    ensure_git_available()
    os.makedirs(REPOSITORY_CACHE_DIR, exist_ok=True)
    target_dir = os.path.join(REPOSITORY_CACHE_DIR, reference.cache_key)

    if os.path.isdir(os.path.join(target_dir, ".git")):
        print(f"Обновляю репозиторий {reference.provider}: {reference.display_name}")
        update_repository(target_dir)
    else:
        if os.path.exists(target_dir):
            raise RuntimeError(f"Путь кеша репозитория уже занят не git-папкой: {target_dir}")
        print(f"Клонирую репозиторий {reference.provider}: {reference.display_name}")
        clone_repository(reference, target_dir)

    return target_dir
