"""URL helpers shared by crawler, audit and agents."""

from urllib.parse import urljoin, urlsplit, urlunsplit


def canon(u: str) -> str:
    """Canonical form for comparing URLs: no fragment, no www, no trailing slash."""
    try:
        p = urlsplit(u)
    except ValueError:
        return u
    host = (p.hostname or "").removeprefix("www.")
    netloc = host if p.port is None else f"{host}:{p.port}"
    path = p.path if p.path in ("", "/") else p.path.rstrip("/")
    return urlunsplit((p.scheme, netloc, path or "/", p.query, ""))


def safe_path(u: str) -> str:
    try:
        return urlsplit(u).path or "/"
    except ValueError:
        return u


def origin_of(u: str) -> str:
    p = urlsplit(u)
    return f"{p.scheme}://{p.netloc}"


def resolve(href: str, base: str) -> str:
    try:
        full = urljoin(base, href)
        p = urlsplit(full)
        return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
    except ValueError:
        return href


def is_internal(href: str, origin: str) -> bool:
    try:
        h = (urlsplit(href).hostname or "").removeprefix("www.")
        o = (urlsplit(origin).hostname or "").removeprefix("www.")
        return bool(h) and h == o
    except ValueError:
        return False


def slug_of(pathname: str) -> str:
    last = pathname.rstrip("/").split("/")[-1]
    for ext in (".html", ".htm", ".php", ".aspx", ".asp"):
        if last.lower().endswith(ext):
            last = last[: -len(ext)]
    return last
