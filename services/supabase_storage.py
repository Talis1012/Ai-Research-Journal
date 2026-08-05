from dataclasses import dataclass
import threading
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

from db.database import get_current_app_user_id
from utils.auth import current_id_token
from utils.query_cache import cached_identity_read
from utils.runtime_config import supabase_publishable_key, supabase_url


STORAGE_SCHEME = "supabase://"
ALLOWED_BUCKETS = {
    "audio",
    "library",
    "analysis-artifacts",
    "manuscript-assets",
}
_http_state = threading.local()


class SupabaseStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StorageObject:
    bucket: str
    key: str

    @property
    def reference(self) -> str:
        return f"{STORAGE_SCHEME}{self.bucket}/{self.key}"


def is_storage_reference(value: str | None) -> bool:
    return str(value or "").startswith(STORAGE_SCHEME)


def _http_session() -> requests.Session:
    session = getattr(_http_state, "session", None)

    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _http_state.session = session

    return session


def current_user_prefix() -> str:
    return f"users/{cached_identity_read(get_current_app_user_id)}"


def user_object_key(relative_path: str) -> str:
    normalized = str(relative_path or "").strip().strip("/")

    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("The storage object path is invalid.")

    return f"{current_user_prefix()}/{normalized}"


def parse_storage_reference(reference: str, *, bucket: str | None = None) -> StorageObject:
    value = str(reference or "").strip()

    if not value.startswith(STORAGE_SCHEME):
        raise ValueError("The value is not a Supabase Storage reference.")

    remainder = value[len(STORAGE_SCHEME):]
    parsed_bucket, separator, key = remainder.partition("/")

    if not separator or parsed_bucket not in ALLOWED_BUCKETS:
        raise ValueError("The Supabase Storage bucket is invalid.")

    if bucket and parsed_bucket != bucket:
        raise ValueError("The object belongs to a different storage bucket.")

    expected_prefix = current_user_prefix() + "/"

    if not key.startswith(expected_prefix) or any(
        part in {"", ".", ".."} for part in key.split("/")
    ):
        raise ValueError("The object is outside the authenticated user's storage area.")

    return StorageObject(parsed_bucket, key)


def _request_headers(*, content_type: str | None = None) -> dict[str, str]:
    publishable_key = supabase_publishable_key()

    if not supabase_url() or not publishable_key:
        raise SupabaseStorageError("Supabase Storage is not configured.")

    headers = {
        "apikey": publishable_key,
        "Authorization": f"Bearer {current_id_token()}",
    }

    if content_type:
        headers["Content-Type"] = content_type

    return headers


def _object_url(bucket: str, key: str = "") -> str:
    encoded_bucket = quote(bucket, safe="")
    suffix = f"/{quote(key, safe='/')}" if key else ""
    return f"{supabase_url()}/storage/v1/object/{encoded_bucket}{suffix}"


def _raise_for_storage(response: requests.Response, action: str):
    if response.ok:
        return

    detail = ""

    try:
        payload = response.json()
        detail = str(
            payload.get("message")
            or payload.get("error")
            or payload.get("statusCode")
            or ""
        ).strip()
    except (ValueError, AttributeError):
        pass

    suffix = f" ({detail[:300]})" if detail else ""
    raise SupabaseStorageError(
        f"Supabase Storage could not {action}: HTTP {response.status_code}{suffix}"
    )


def upload_bytes(
    bucket: str,
    relative_path: str,
    content: bytes,
    *,
    content_type: str,
    upsert: bool = False,
) -> str:
    if bucket not in ALLOWED_BUCKETS:
        raise ValueError("The storage bucket is not allowed.")

    key = user_object_key(relative_path)
    headers = _request_headers(content_type=content_type)
    headers["cache-control"] = "3600"
    headers["x-upsert"] = "true" if upsert else "false"
    response = _http_session().post(
        _object_url(bucket, key),
        headers=headers,
        data=content,
        timeout=(10, 90),
    )
    _raise_for_storage(response, "upload the object")
    return StorageObject(bucket, key).reference


def download_bytes(reference: str, *, bucket: str | None = None) -> bytes:
    stored = parse_storage_reference(reference, bucket=bucket)
    response = _http_session().get(
        _object_url(stored.bucket, stored.key),
        headers=_request_headers(),
        timeout=(10, 90),
    )
    _raise_for_storage(response, "download the object")
    return response.content


def delete_object(reference: str | None, *, bucket: str | None = None):
    if not reference:
        return

    stored = parse_storage_reference(reference, bucket=bucket)
    response = _http_session().delete(
        _object_url(stored.bucket),
        headers=_request_headers(content_type="application/json"),
        json={"prefixes": [stored.key]},
        timeout=(10, 60),
    )
    _raise_for_storage(response, "delete the object")


def create_signed_url(
    reference: str,
    *,
    bucket: str | None = None,
    expires_in: int = 300,
) -> str:
    stored = parse_storage_reference(reference, bucket=bucket)
    expires_in = max(60, min(int(expires_in), 3600))
    response = _http_session().post(
        f"{supabase_url()}/storage/v1/object/sign/"
        f"{quote(stored.bucket, safe='')}/{quote(stored.key, safe='/')}",
        headers=_request_headers(content_type="application/json"),
        json={"expiresIn": expires_in},
        timeout=(10, 30),
    )
    _raise_for_storage(response, "create a signed object URL")
    payload = response.json()
    signed_path = str(payload.get("signedURL") or payload.get("signedUrl") or "")

    if not signed_path:
        raise SupabaseStorageError("Supabase Storage returned no signed object URL.")

    if signed_path.startswith(("https://", "http://")):
        return signed_path

    if signed_path.startswith("/storage/v1/"):
        return f"{supabase_url().rstrip('/')}{signed_path}"

    if signed_path.startswith("/object/"):
        return f"{supabase_url().rstrip('/')}/storage/v1{signed_path}"

    return f"{supabase_url().rstrip('/')}/storage/v1/{signed_path.lstrip('/')}"


def _list_folder(bucket: str, prefix: str) -> list[dict]:
    objects = []
    offset = 0
    page_size = 100

    while True:
        response = _http_session().post(
            f"{supabase_url()}/storage/v1/object/list/{quote(bucket, safe='')}",
            headers=_request_headers(content_type="application/json"),
            json={
                "prefix": prefix.strip("/"),
                "limit": page_size,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
            timeout=(10, 60),
        )
        _raise_for_storage(response, "list objects")
        page = response.json()

        if not isinstance(page, list):
            raise SupabaseStorageError("Supabase Storage returned an invalid object list.")

        objects.extend(page)

        if len(page) < page_size:
            break

        offset += page_size

    return objects


def _walk_user_objects(
    bucket: str,
    relative_prefix: str = "",
) -> list[tuple[str, dict]]:
    if bucket not in ALLOWED_BUCKETS:
        raise ValueError("The storage bucket is not allowed.")

    root = current_user_prefix()
    initial = f"{root}/{relative_prefix.strip('/')}".rstrip("/")
    pending = [initial]
    found: list[tuple[str, dict]] = []

    while pending:
        folder = pending.pop()

        for entry in _list_folder(bucket, folder):
            name = str(entry.get("name") or "").strip().strip("/")

            if not name or "/" in name:
                continue

            child = f"{folder}/{name}"

            if entry.get("id") is None:
                pending.append(child)
            else:
                found.append((child, entry))

    return found


def list_user_objects(bucket: str, relative_prefix: str = "") -> list[str]:
    return [key for key, _ in _walk_user_objects(bucket, relative_prefix)]


def user_storage_usage(bucket: str, relative_prefix: str = "") -> tuple[int, int]:
    total_bytes = 0
    objects = _walk_user_objects(bucket, relative_prefix)

    for _, entry in objects:
        metadata = entry.get("metadata")

        if isinstance(metadata, dict):
            try:
                total_bytes += max(0, int(metadata.get("size") or 0))
            except (TypeError, ValueError):
                pass

    return total_bytes, len(objects)


def storage_object_size(reference: str, *, bucket: str | None = None) -> int:
    stored = parse_storage_reference(reference, bucket=bucket)
    folder, _, filename = stored.key.rpartition("/")

    for entry in _list_folder(stored.bucket, folder):
        if str(entry.get("name") or "") != filename:
            continue

        metadata = entry.get("metadata")

        if isinstance(metadata, dict):
            try:
                return max(0, int(metadata.get("size") or 0))
            except (TypeError, ValueError):
                return 0

    return 0


def enforce_user_storage_quota(
    bucket: str,
    incoming_bytes: int,
    *,
    quota_bytes: int,
    label: str,
    max_files: int | None = None,
    incoming_files: int = 1,
    reclaim_bytes: int = 0,
    replacing_files: int = 0,
):
    from services.resource_limits import ResourceLimitError

    used_bytes, file_count = user_storage_usage(bucket)
    effective_bytes = max(0, used_bytes - max(0, int(reclaim_bytes)))
    effective_files = max(0, file_count - max(0, int(replacing_files)))

    if effective_bytes + max(0, int(incoming_bytes)) > quota_bytes:
        quota_mb = quota_bytes // (1024 * 1024)
        raise ResourceLimitError(
            f"The {label} storage quota of {quota_mb} MB would be exceeded."
        )

    if (
        max_files is not None
        and effective_files + max(0, int(incoming_files)) > max_files
    ):
        raise ResourceLimitError(
            f"The {label} limit of {max_files} stored files has been reached."
        )


def delete_user_objects(bucket: str, relative_prefix: str = ""):
    keys = list_user_objects(bucket, relative_prefix)

    for index in range(0, len(keys), 100):
        response = _http_session().delete(
            _object_url(bucket),
            headers=_request_headers(content_type="application/json"),
            json={"prefixes": keys[index:index + 100]},
            timeout=(10, 90),
        )
        _raise_for_storage(response, "delete stored objects")
