from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def object_storage_is_configured() -> bool:
    required_values = (
        getattr(settings, "AI_CHAT_OBJECT_STORAGE_ENDPOINT", ""),
        getattr(settings, "AI_CHAT_OBJECT_STORAGE_ACCESS_KEY", ""),
        getattr(settings, "AI_CHAT_OBJECT_STORAGE_SECRET_KEY", ""),
        getattr(settings, "AI_CHAT_OBJECT_STORAGE_BUCKET", ""),
    )
    return all(isinstance(value, str) and value.strip() for value in required_values)


class ObjectStorage:
    def __init__(self) -> None:
        if not object_storage_is_configured():
            raise ImproperlyConfigured(
                "Answer photo storage is not configured. Set the AI_CHAT_OBJECT_STORAGE_* settings."
            )

        self.endpoint = settings.AI_CHAT_OBJECT_STORAGE_ENDPOINT.strip()
        self.access_key = settings.AI_CHAT_OBJECT_STORAGE_ACCESS_KEY.strip()
        self.secret_key = settings.AI_CHAT_OBJECT_STORAGE_SECRET_KEY.strip()
        self.bucket = settings.AI_CHAT_OBJECT_STORAGE_BUCKET.strip()
        self.region = getattr(settings, "AI_CHAT_OBJECT_STORAGE_REGION", "us-east-1")

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return False
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in {"404", "NoSuchBucket"}:
                raise

        create_kwargs = {"Bucket": self.bucket}
        if self.region and self.region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self.client.create_bucket(**create_kwargs)
        return True

    def put_object(self, *, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def get_object_bytes(self, *, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete_object(self, *, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache(maxsize=1)
def get_object_storage() -> ObjectStorage:
    return ObjectStorage()
