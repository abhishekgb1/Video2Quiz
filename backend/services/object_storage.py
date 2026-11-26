"""Private branch-scoped S3 storage; credentials never reach the frontend."""
import mimetypes
import os
from functools import lru_cache
from pathlib import Path
from uuid import uuid4


def enabled():
    return bool(os.getenv("MEDIA_BUCKET", "").strip())


@lru_cache(maxsize=1)
def client():
    import boto3
    from botocore.config import Config
    endpoint = os.environ["AWS_ENDPOINT_URL_S3"]
    if not endpoint.startswith("https://"):
        raise RuntimeError("Media storage must use an HTTPS endpoint.")
    return boto3.client("s3", endpoint_url=endpoint, region_name=os.environ["AWS_REGION"],
                        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                                      retries={"mode": "standard", "total_max_attempts": 3},
                                      connect_timeout=10, read_timeout=60,
                                      request_checksum_calculation="when_required",
                                      response_checksum_validation="when_required"))


def upload(path: Path, video_id: int, kind: str):
    from boto3.s3.transfer import TransferConfig
    key = f"videos/{video_id}/{kind}/{uuid4().hex}{path.suffix.lower()}"
    client().upload_file(str(path), os.environ["MEDIA_BUCKET"], key,
                         ExtraArgs={"ContentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                                    "CacheControl": "private, max-age=300"},
                         Config=TransferConfig(max_concurrency=2, use_threads=False))
    return key


def signed_playback(key):
    if not key or not key.startswith("videos/") or ".." in key.split("/"):
        raise ValueError("Invalid stored media key.")
    return client().generate_presigned_url("get_object", Params={"Bucket": os.environ["MEDIA_BUCKET"], "Key": key}, ExpiresIn=3600)


def restore_original(key, destination: Path):
    client().download_file(os.environ["MEDIA_BUCKET"], key, str(destination))
