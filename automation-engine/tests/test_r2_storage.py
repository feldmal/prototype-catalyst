from unittest.mock import Mock

import pytest

from app.r2_storage import (
    DEFAULT_PART_SIZE,
    MIB,
    R2Storage,
    UploadSizeError,
)


@pytest.fixture
def client():
    return Mock()


@pytest.fixture
def storage(client):
    client.create_multipart_upload.return_value = {"UploadId": "upload-123"}
    return R2Storage(client=client, bucket="private-test-bucket")


def test_initiate_multipart_creates_upload(storage, client):
    upload = storage.initiate_multipart(
        "incoming/job/file.csv", "text/csv", 20 * MIB
    )
    assert upload.upload_id == "upload-123"
    assert upload.part_count == 2
    assert upload.part_size == DEFAULT_PART_SIZE
    client.create_multipart_upload.assert_called_once_with(
        Bucket="private-test-bucket",
        Key="incoming/job/file.csv",
        ContentType="text/csv",
    )


def test_rejects_zero_or_oversized_file(storage):
    with pytest.raises(UploadSizeError):
        storage.initiate_multipart("x.csv", "text/csv", 0)
    with pytest.raises(UploadSizeError):
        storage.initiate_multipart("x.csv", "text/csv", 1025 * MIB)


def test_rejects_small_parts(storage):
    with pytest.raises(UploadSizeError):
        storage.initiate_multipart("x.csv", "text/csv", 10 * MIB, part_size=4 * MIB)


def test_part_url_is_limited_to_expected_part_numbers(storage, client):
    upload = storage.initiate_multipart("x.csv", "text/csv", 20 * MIB)
    client.generate_presigned_url.return_value = "https://example.invalid/part"
    url = storage.create_part_url(upload, 2)
    assert url == "https://example.invalid/part"
    assert client.generate_presigned_url.call_args.kwargs["Params"]["PartNumber"] == 2
    with pytest.raises(ValueError):
        storage.create_part_url(upload, 3)


def test_complete_requires_all_ordered_parts(storage, client):
    upload = storage.initiate_multipart("x.csv", "text/csv", 20 * MIB)
    with pytest.raises(ValueError):
        storage.complete_multipart(upload, [{"PartNumber": 1, "ETag": "etag-1"}])
    result_parts = [
        {"PartNumber": 1, "ETag": "etag-1"},
        {"PartNumber": 2, "ETag": "etag-2"},
    ]
    storage.complete_multipart(upload, result_parts)
    assert client.complete_multipart_upload.call_args.kwargs["MultipartUpload"] == {
        "Parts": result_parts
    }


def test_abort_and_download_url(storage, client):
    upload = storage.initiate_multipart("x.csv", "text/csv", 20 * MIB)
    storage.abort_multipart(upload)
    client.abort_multipart_upload.assert_called_once()
    client.generate_presigned_url.return_value = "https://example.invalid/download"
    assert storage.create_download_url("result.csv") == "https://example.invalid/download"
