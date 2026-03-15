from typing import Annotated
from urllib.parse import quote, unquote
from xml.etree import ElementTree as ET

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from mcps.config import settings
from mcps.shared.pagination import DEFAULT_LIMIT, TsvList, paginate
from mcps.shared.query import apply_query, project, to_tsv
from mcps.shared.schema import optimize_tool_schemas

mcp = FastMCP("Storage")

DAV_NS = {"D": "DAV:"}


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.webdav_url.rstrip("/"),
        auth=(settings.webdav_user, settings.webdav_pass),
        timeout=30.0,
    )


class FileEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int
    size_mb: float


class DirListing(BaseModel):
    path: str
    entries: list[FileEntry] | list[dict]
    total: int
    offset: int
    has_more: bool


def _propfind(path: str, depth: int = 1) -> list[FileEntry]:
    """PROPFIND on a path, return parsed entries."""
    # Ensure path is properly encoded for WebDAV
    encoded = "/" + "/".join(quote(seg, safe="") for seg in path.strip("/").split("/") if seg) + "/"
    if path in ("", "/"):
        encoded = "/"

    with _client() as c:
        resp = c.request("PROPFIND", encoded, headers={"Depth": str(depth)})
        resp.raise_for_status()

    tree = ET.fromstring(resp.text)
    entries = []
    for r in tree.findall(".//D:response", DAV_NS):
        href = r.find("D:href", DAV_NS).text
        # Skip the directory itself
        decoded = unquote(href)
        # Strip the webdav prefix to get a clean path
        clean = decoded.replace("/webdav/", "/", 1).rstrip("/") or "/"
        parent_clean = unquote(encoded).replace("/webdav/", "/", 1).rstrip("/") or "/"
        if clean == parent_clean:
            continue

        is_dir = r.find(".//D:collection", DAV_NS) is not None
        size_el = r.find(".//D:getcontentlength", DAV_NS)
        size = int(size_el.text) if size_el is not None else 0

        name = clean.rstrip("/").split("/")[-1]
        # Skip hidden/system files
        if name.startswith("."):
            continue

        # Directories report filesystem block size, not content size
        file_size = 0 if is_dir else size
        entries.append(FileEntry(
            name=name,
            path=clean + ("/" if is_dir else ""),
            is_dir=is_dir,
            size=file_size,
            size_mb=round(file_size / (1024 * 1024), 1),
        ))
    return entries


@mcp.tool
def list_dir(
    path: Annotated[str, Field(description="Directory path, e.g. '/' or '/media/movies/'")] = "/",
    filter_expr: Annotated[str | None, Field(description="JMESPath filter, e.g. is_dir==`true`, search(@, 'avatar')")] = None,
    fields: Annotated[list[str] | None, Field(description="Columns to show (name auto-incl.)")] = None,
    sort_by: Annotated[str | None, Field(description="Sort field, - prefix for desc. e.g. -size")] = None,
    limit: Annotated[int, Field()] = DEFAULT_LIMIT,
    offset: Annotated[int, Field()] = 0,
) -> TsvList:
    """List files and directories. Root has: media/ (movies/, tv/, torrents/), Dasha/.
    Fields: name, path, is_dir, size, size_mb."""
    entries = _propfind(path)
    filtered = apply_query(entries, filter_expr, sort_by, limit=None)
    paginated, total, has_more = paginate(filtered, limit, offset)
    result = project(paginated, fields)
    return TsvList(data=to_tsv(result), total=total, offset=offset, has_more=has_more)


def _walk(path: str) -> list[FileEntry]:
    """Recursively list all entries via iterative Depth:1 PROPFIND calls."""
    all_entries: list[FileEntry] = []
    dirs_to_visit = [path]
    while dirs_to_visit:
        current = dirs_to_visit.pop()
        entries = _propfind(current, depth=1)
        for e in entries:
            all_entries.append(e)
            if e.is_dir:
                dirs_to_visit.append(e.path)
    return all_entries


@mcp.tool
def get_dir_size(
    path: Annotated[str, Field(description="Directory path to measure")],
) -> dict:
    """Get total size of a directory (recursive). May be slow for large dirs."""
    entries = _walk(path)
    total = sum(e.size for e in entries if not e.is_dir)
    count_files = sum(1 for e in entries if not e.is_dir)
    count_dirs = sum(1 for e in entries if e.is_dir)
    return {
        "path": path,
        "total_bytes": total,
        "total_gb": round(total / (1024**3), 2),
        "file_count": count_files,
        "dir_count": count_dirs,
    }


@mcp.tool
def delete(
    path: Annotated[str, Field(description="File or directory path to delete")],
) -> bool:
    """Delete a file or directory (recursive). IRREVERSIBLE."""
    encoded = "/" + "/".join(quote(seg, safe="") for seg in path.strip("/").split("/") if seg)
    with _client() as c:
        resp = c.request("DELETE", encoded)
        resp.raise_for_status()
    return True


@mcp.tool
def move(
    src: Annotated[str, Field(description="Source path")],
    dst: Annotated[str, Field(description="Destination path")],
) -> bool:
    """Move/rename a file or directory."""
    src_encoded = "/" + "/".join(quote(seg, safe="") for seg in src.strip("/").split("/") if seg)
    dst_encoded = settings.webdav_url.rstrip("/") + "/" + "/".join(quote(seg, safe="") for seg in dst.strip("/").split("/") if seg)
    with _client() as c:
        resp = c.request("MOVE", src_encoded, headers={"Destination": dst_encoded})
        resp.raise_for_status()
    return True


optimize_tool_schemas(mcp)
