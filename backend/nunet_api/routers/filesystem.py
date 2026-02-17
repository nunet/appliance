import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from modules.path_constants import FILESYSTEM_ALLOWED_ROOTS, FILESYSTEM_ROOT

from ..schemas import (
    FilesystemCopyRequest,
    FilesystemCreateFolderRequest,
    FilesystemDeleteRequest,
    FilesystemEntry,
    FilesystemListResponse,
    FilesystemMoveRequest,
    FilesystemOperationItem,
    FilesystemOperationResponse,
    FilesystemUploadItem,
    FilesystemUploadResponse,
    SimpleStatusResponse,
)

router = APIRouter()

ROOT_DIR = FILESYSTEM_ROOT.expanduser().resolve()


def _set_no_store(response: Response) -> None:
    # Avoid caching potentially sensitive file metadata in the browser/proxies.
    response.headers["Cache-Control"] = "no-store"


def _is_inside(base: Path, path: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


_allowed_roots_raw = [path.expanduser().resolve() for path in FILESYSTEM_ALLOWED_ROOTS]
ALLOWED_ROOTS = sorted({path for path in _allowed_roots_raw if _is_inside(ROOT_DIR, path)}, key=lambda p: str(p))


def _compute_listable_dirs() -> set[Path]:
    dirs = {ROOT_DIR}
    for root in ALLOWED_ROOTS:
        current = root
        while True:
            dirs.add(current)
            if current == ROOT_DIR:
                break
            parent = current.parent
            if parent == current:
                break
            current = parent
    return dirs


LISTABLE_DIRS = _compute_listable_dirs()


def _is_inside_root(path: Path) -> bool:
    return _is_inside(ROOT_DIR, path)


def _matching_allowed_root(path: Path) -> Optional[Path]:
    for root in ALLOWED_ROOTS:
        if _is_inside(root, path):
            return root
    return None


def _ensure_list_allowed(path: Path) -> None:
    if _matching_allowed_root(path) is not None:
        return
    if path in LISTABLE_DIRS:
        return
    raise HTTPException(status_code=403, detail="Path is not allowed")


def _ensure_operation_allowed(path: Path) -> None:
    if _matching_allowed_root(path) is None:
        raise HTTPException(status_code=403, detail="Path is not allowed")


def _allowed_children_for_dir(dir_path: Path) -> Optional[set[Path]]:
    """
    For bridge directories (ancestors of allowed roots), only expose the next
    path segment needed to reach an allowed root.
    Returns None when no filtering is required (dir_path is within an allowed root).
    """
    if _matching_allowed_root(dir_path) is not None:
        return None

    allowed_children: set[Path] = set()
    for root in ALLOWED_ROOTS:
        try:
            rel = root.relative_to(dir_path)
        except ValueError:
            continue
        if not rel.parts:
            continue
        allowed_children.add(dir_path / rel.parts[0])
    return allowed_children


def _abs_path(path_str: Optional[str]) -> Path:
    if path_str is None or str(path_str).strip() == "":
        return ROOT_DIR
    candidate = Path(str(path_str)).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    abs_path = candidate.absolute()
    if not _is_inside_root(abs_path):
        raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")
    return abs_path


def _resolve_existing_path(
    path_str: str,
    *,
    allow_symlink: bool = False,
    purpose: str = "op",
) -> Path:
    abs_path = _abs_path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if abs_path.is_symlink():
        if allow_symlink:
            return abs_path
        raise HTTPException(status_code=400, detail="Symlink paths are not supported")
    resolved = abs_path.resolve()
    if not _is_inside_root(resolved):
        raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")

    if purpose == "list":
        _ensure_list_allowed(resolved)
    else:
        _ensure_operation_allowed(resolved)
    return resolved


def _ensure_parent_inside(path: Path) -> None:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    if current.exists():
        resolved = current.resolve()
        if not _is_inside_root(resolved):
            raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")


def _ensure_parent_allowed(path: Path) -> None:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    if current.exists():
        resolved = current.resolve()
        if not _is_inside_root(resolved):
            raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")
        _ensure_operation_allowed(resolved)


def _sanitize_filename(name: str) -> str:
    raw = name.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if "/" in raw or "\\" in raw:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if raw in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return raw


def _format_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _entry_info(entry: Path) -> FilesystemEntry:
    stat = entry.lstat()
    is_symlink = entry.is_symlink()
    is_dir = entry.is_dir() if not is_symlink else False
    is_file = entry.is_file() if not is_symlink else False
    entry_path = entry.absolute()
    rel = ""
    try:
        rel = str(entry_path.relative_to(ROOT_DIR))
    except ValueError:
        rel = entry.name
    return FilesystemEntry(
        name=entry.name,
        path=str(entry_path),
        relative_path=rel,
        is_dir=is_dir,
        is_file=is_file,
        is_symlink=is_symlink,
        size=None if is_dir else stat.st_size,
        modified_at=_format_mtime(stat.st_mtime),
    )


def _aggregate_status(items: List[FilesystemOperationItem]) -> tuple[str, str]:
    total = len(items)
    success = sum(1 for item in items if item.status == "success")
    if success == total and total > 0:
        return "success", f"{success} succeeded"
    if success == 0:
        return "error", "No operations succeeded"
    return "partial", f"{success} of {total} succeeded"


@router.get("/list", response_model=FilesystemListResponse)
def list_filesystem(
    response: Response,
    path: Optional[str] = Query(None, description="Path under allowed roots"),
):
    _set_no_store(response)
    target = _resolve_existing_path(path or str(ROOT_DIR), purpose="list")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    rel = str(target.relative_to(ROOT_DIR)) if target != ROOT_DIR else "."
    parent = None
    if target != ROOT_DIR:
        parent = str(target.parent)
    entries = list(target.iterdir())
    allowed_children = _allowed_children_for_dir(target)
    if allowed_children is not None:
        entries = [entry for entry in entries if entry.absolute() in allowed_children]

    items = [_entry_info(entry) for entry in entries]
    items.sort(key=lambda item: (not item.is_dir, item.name.lower()))
    return FilesystemListResponse(
        root=str(ROOT_DIR),
        path=str(target),
        relative_path=rel,
        parent=parent,
        items=items,
    )


@router.post("/upload", response_model=FilesystemUploadResponse)
def upload_files(
    response: Response,
    files: List[UploadFile] = File(..., description="Files to upload"),
    path: Optional[str] = Form(None, description="Destination directory under allowed roots"),
    overwrite: bool = Form(False),
):
    _set_no_store(response)
    dest_dir = _abs_path(path)
    _ensure_operation_allowed(dest_dir)
    if dest_dir.exists():
        if not dest_dir.is_dir():
            raise HTTPException(status_code=400, detail="Destination is not a directory")
        if dest_dir.is_symlink():
            raise HTTPException(status_code=400, detail="Destination cannot be a symlink")
        resolved_dest = dest_dir.resolve()
        if not _is_inside_root(resolved_dest):
            raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")
        _ensure_operation_allowed(resolved_dest)
    else:
        _ensure_parent_allowed(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

    items: List[FilesystemUploadItem] = []
    errors: List[str] = []
    for upload in files:
        filename = upload.filename or "unknown"
        try:
            filename = _sanitize_filename(filename)
            target = dest_dir / filename
            existed_before = target.exists()
            if target.exists() and not overwrite:
                raise HTTPException(status_code=409, detail=f"File already exists: {filename}")
            if target.exists() and target.is_dir():
                raise HTTPException(status_code=409, detail=f"Directory exists with name: {filename}")

            _ensure_parent_allowed(target)
            with open(target, "wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            try:
                upload.file.close()
            except Exception:
                pass

            stat = target.stat()
            rel = str(target.absolute().relative_to(ROOT_DIR))
            items.append(
                FilesystemUploadItem(
                    name=filename,
                    path=str(target),
                    relative_path=rel,
                    size=stat.st_size,
                    modified_at=_format_mtime(stat.st_mtime),
                    overwritten=existed_before and overwrite,
                )
            )
        except HTTPException as exc:
            errors.append(f"{filename}: {exc.detail}")
        except Exception as exc:  # noqa: BLE001 - surface upload errors
            errors.append(f"{upload.filename}: {exc}")

    status = "success" if not errors else ("error" if not items else "partial")
    message = (
        "Files uploaded successfully"
        if status == "success"
        else "Some files failed to upload"
        if status == "partial"
        else "No files uploaded"
    )
    return FilesystemUploadResponse(status=status, message=message, items=items, errors=errors or None)


@router.post("/copy", response_model=FilesystemOperationResponse)
def copy_files(payload: FilesystemCopyRequest, response: Response):
    _set_no_store(response)
    if not payload.sources:
        raise HTTPException(status_code=400, detail="No sources provided")

    dest = _abs_path(payload.destination)
    _ensure_operation_allowed(dest)
    dest_exists = dest.exists()
    dest_is_dir = dest_exists and dest.is_dir()

    if len(payload.sources) > 1 and not dest_is_dir:
        raise HTTPException(status_code=400, detail="Destination must be a directory for multiple sources")

    if dest_exists:
        resolved_dest = dest.resolve()
        if not _is_inside_root(resolved_dest):
            raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")
        _ensure_operation_allowed(resolved_dest)
        if dest.is_symlink():
            raise HTTPException(status_code=400, detail="Destination cannot be a symlink")
    else:
        _ensure_parent_allowed(dest)

    items: List[FilesystemOperationItem] = []
    for source in payload.sources:
        try:
            src = _resolve_existing_path(source, purpose="op")
            if dest_is_dir:
                target = dest / src.name
            else:
                target = dest
            _ensure_parent_allowed(target)

            if target.exists() and not payload.overwrite:
                raise HTTPException(status_code=409, detail="Destination already exists")
            if src.is_dir():
                if target.exists() and not target.is_dir():
                    raise HTTPException(status_code=409, detail="Destination exists and is not a directory")
                shutil.copytree(src, target, symlinks=True, dirs_exist_ok=payload.overwrite)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)

            items.append(
                FilesystemOperationItem(
                    source=str(src),
                    destination=str(target),
                    status="success",
                )
            )
        except HTTPException as exc:
            items.append(
                FilesystemOperationItem(
                    source=str(source),
                    destination=str(dest),
                    status="error",
                    message=str(exc.detail),
                )
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                FilesystemOperationItem(
                    source=str(source),
                    destination=str(dest),
                    status="error",
                    message=str(exc),
                )
            )

    status, message = _aggregate_status(items)
    return FilesystemOperationResponse(status=status, message=message, items=items)


@router.post("/move", response_model=FilesystemOperationResponse)
def move_files(payload: FilesystemMoveRequest, response: Response):
    _set_no_store(response)
    if not payload.sources:
        raise HTTPException(status_code=400, detail="No sources provided")

    dest = _abs_path(payload.destination)
    _ensure_operation_allowed(dest)
    dest_exists = dest.exists()
    dest_is_dir = dest_exists and dest.is_dir()

    if len(payload.sources) > 1 and not dest_is_dir:
        raise HTTPException(status_code=400, detail="Destination must be a directory for multiple sources")

    if dest_exists:
        resolved_dest = dest.resolve()
        if not _is_inside_root(resolved_dest):
            raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")
        _ensure_operation_allowed(resolved_dest)
        if dest.is_symlink():
            raise HTTPException(status_code=400, detail="Destination cannot be a symlink")
    else:
        _ensure_parent_allowed(dest)

    items: List[FilesystemOperationItem] = []
    for source in payload.sources:
        try:
            src = _resolve_existing_path(source, purpose="op")
            target = dest / src.name if dest_is_dir else dest
            _ensure_parent_allowed(target)

            if target.exists():
                if not payload.overwrite:
                    raise HTTPException(status_code=409, detail="Destination already exists")
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))

            items.append(
                FilesystemOperationItem(
                    source=str(src),
                    destination=str(target),
                    status="success",
                )
            )
        except HTTPException as exc:
            items.append(
                FilesystemOperationItem(
                    source=str(source),
                    destination=str(dest),
                    status="error",
                    message=str(exc.detail),
                )
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                FilesystemOperationItem(
                    source=str(source),
                    destination=str(dest),
                    status="error",
                    message=str(exc),
                )
            )

    status, message = _aggregate_status(items)
    return FilesystemOperationResponse(status=status, message=message, items=items)


@router.delete("", response_model=FilesystemOperationResponse)
def delete_files(payload: FilesystemDeleteRequest, response: Response):
    _set_no_store(response)
    if not payload.paths:
        raise HTTPException(status_code=400, detail="No paths provided")

    items: List[FilesystemOperationItem] = []
    for path_str in payload.paths:
        try:
            abs_path = _abs_path(path_str)
            _ensure_operation_allowed(abs_path)
            if abs_path.is_symlink():
                abs_path.unlink()
                items.append(
                    FilesystemOperationItem(
                        source=str(abs_path),
                        status="success",
                    )
                )
                continue
            if not abs_path.exists():
                raise HTTPException(status_code=404, detail="Path not found")

            resolved = abs_path.resolve()
            if not _is_inside_root(resolved):
                raise HTTPException(status_code=400, detail=f"Path must be inside {ROOT_DIR}")
            _ensure_operation_allowed(resolved)

            if resolved.is_dir():
                if not payload.recursive:
                    raise HTTPException(status_code=400, detail="Recursive delete required for directories")
                shutil.rmtree(resolved)
            else:
                resolved.unlink()

            items.append(
                FilesystemOperationItem(
                    source=str(resolved),
                    status="success",
                )
            )
        except HTTPException as exc:
            items.append(
                FilesystemOperationItem(
                    source=str(path_str),
                    status="error",
                    message=str(exc.detail),
                )
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                FilesystemOperationItem(
                    source=str(path_str),
                    status="error",
                    message=str(exc),
                )
            )

    status, message = _aggregate_status(items)
    return FilesystemOperationResponse(status=status, message=message, items=items)


@router.get("/download")
def download_file(path: str = Query(..., description="File path under allowed roots")):
    target = _resolve_existing_path(path, purpose="op")
    if target.is_symlink():
        raise HTTPException(status_code=400, detail="Symlink paths are not supported")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Directories are not supported for download")
    resp = FileResponse(path=str(target), filename=target.name)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/folder", response_model=SimpleStatusResponse)
def create_folder(payload: FilesystemCreateFolderRequest, response: Response):
    _set_no_store(response)
    target = _abs_path(payload.path)
    _ensure_operation_allowed(target)
    if target.exists():
        if target.is_symlink():
            raise HTTPException(status_code=400, detail="Symlink paths are not supported")
        if target.is_dir():
            if payload.exist_ok:
                return SimpleStatusResponse(status="success", message="Folder already exists")
            raise HTTPException(status_code=409, detail="Folder already exists")
        raise HTTPException(status_code=409, detail="File exists at path")

    _ensure_parent_allowed(target)
    target.mkdir(parents=payload.parents, exist_ok=payload.exist_ok)
    return SimpleStatusResponse(status="success", message="Folder created")
