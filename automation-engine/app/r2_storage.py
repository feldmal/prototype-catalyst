"""Cloudflare R2 multipart-storage adapter.

This module deliberately contains no HTTP routes or credentials. It provides the
storage primitives that the authenticated upload/job lifecycle can call. R2 is
S3-compatible; boto3 is configured with the account-specific endpoint.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config

MIB = 1024 * 1024
MIN_PART_SIZE = 5 * MIB
DEFAULT_PART_SIZE = 16 * MIB
MAX_PARTS = 10_000
MAX_OBJECT_SIZE = int(os.getenv("R2_MAX_UPLOAD_MB", "1024")) * MIB


class R2ConfigurationError(RuntimeError):
    """Raised when R2 is selected but required settings are missing."""


class UploadSizeError(ValueError):
    """Raised when a requested multipart upload exceeds configured limits."""


@dataclass(frozen=True)
class MultipartUpload:
    bucket: str
    key: str
    upload_id: str
    part_size: int
    part_count: int
    max_object_size: int


class R2Storage:
    """Small S3-compatible adapter for private Cloudflare R2 buckets."""

    def __init__(self, client: Any | None = None, bucket: str | None = None):
        self.bucket = bucket or os.getenv("R2_BUCKET")
        if not self.bucket:
            raise R2ConfigurationError("R2_BUCKET is required.")
        if client is None:
            account_id = os.getenv("R2_ACCOUNT_ID")
            access_key = os.getenv("R2_ACCESS_KEY_ID")
            secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
            if not all((account_id, access_key, secret_key)):
                raise R2ConfigurationError(
                    "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY are required."
                )
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name="auto",
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        self.client = client

    def initiate_multipart(
        self,
        key: str,
        content_type: str,
        expected_size: int,
        part_size: int = DEFAULT_PART_SIZE,
    ) -> MultipartUpload:
        if expected_size <= 0:
            raise UploadSizeError("File size must be greater than zero.")
        if expected_size > MAX_OBJECT_SIZE:
            raise UploadSizeError(
                f"File exceeds configured limit of {MAX_OBJECT_SIZE // MIB} MB."
            )
        if part_size < MIN_PART_SIZE:
            raise UploadSizeError("Multipart part size must be at least 5 MiB.")
        part_count = math.ceil(expected_size / part_size)
        if part_count > MAX_PARTS:
            raise UploadSizeError("Upload requires more than 10,000 parts.")
        response = self.client.create_multipart_upload(
            Bucket=self.bucket, Key=key, ContentType=content_type
        )
        return MultipartUpload(
            bucket=self.bucket,
            key=key,
            upload_id=response["UploadId"],
            part_size=part_size,
            part_count=part_count,
            max_object_size=MAX_OBJECT_SIZE,
        )

    def create_part_url(
        self, upload: MultipartUpload, part_number: int, expires_in: int = 900
    ) -> str:
        if not 1 <= part_number <= upload.part_count:
            raise ValueError("Part number is outside the upload range.")
        if not 1 <= expires_in <= 3600:
            raise ValueError("Presigned URL expiry must be between 1 and 3600 seconds.")
        return self.client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": upload.bucket,
                "Key": upload.key,
                "UploadId": upload.upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )

    def complete_multipart(
        self, upload: MultipartUpload, parts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if len(parts) != upload.part_count:
            raise ValueError("The completed part list does not match the expected part count.")
        normalized: list[dict[str, Any]] = []
        for expected, part in enumerate(parts, start=1):
            if part.get("PartNumber") != expected or not part.get("ETag"):
                raise ValueError("Parts must be ordered and include each part number and ETag.")
            normalized.append({"PartNumber": expected, "ETag": part["ETag"]})
        return self.client.complete_multipart_upload(
            Bucket=upload.bucket,
            Key=upload.key,
            UploadId=upload.upload_id,
            MultipartUpload={"Parts": normalized},
        )

    def abort_multipart(self, upload: MultipartUpload) -> None:
        self.client.abort_multipart_upload(
            Bucket=upload.bucket, Key=upload.key, UploadId=upload.upload_id
        )

    def download_file(self, key: str, destination: str) -> None:
        self.client.download_file(self.bucket, key, destination)

    def head_object(self, key: str) -> dict[str, Any]:
        return self.client.head_object(Bucket=self.bucket, Key=key)

    def upload_file(self, source: str, key: str, content_type: str) -> None:
        self.client.upload_file(
            source, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def create_download_url(self, key: str, expires_in: int = 900) -> str:
        if not 1 <= expires_in <= 3600:
            raise ValueError("Presigned URL expiry must be between 1 and 3600 seconds.")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
            HttpMethod="GET",
        )
