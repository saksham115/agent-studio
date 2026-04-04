"""S3-compatible object storage service (works with MinIO and AWS S3)."""

import logging
import uuid
from io import BytesIO

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Upload, download, and manage files in S3-compatible storage (MinIO/AWS S3)."""

    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.AWS_REGION,
            config=BotoConfig(signature_version="s3v4"),
        )

    def upload_file(self, file_content: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        """Upload a file to S3. Returns the S3 key."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=file_content,
            ContentType=content_type,
        )
        logger.info("Uploaded %s to s3://%s/%s (%d bytes)", key, self.bucket, key, len(file_content))
        return key

    def download_file(self, key: str) -> bytes:
        """Download a file from S3. Returns the file bytes."""
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        data = response["Body"].read()
        logger.info("Downloaded s3://%s/%s (%d bytes)", self.bucket, key, len(data))
        return data

    def delete_file(self, key: str) -> None:
        """Delete a file from S3."""
        self.client.delete_object(Bucket=self.bucket, Key=key)
        logger.info("Deleted s3://%s/%s", self.bucket, key)

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access to a file."""
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    def file_exists(self, key: str) -> bool:
        """Check if a file exists in S3."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    @staticmethod
    def generate_key(agent_id: str | uuid.UUID, filename: str) -> str:
        """Generate a unique S3 key for a file."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        unique_id = uuid.uuid4().hex[:12]
        return f"agents/{agent_id}/documents/{unique_id}.{ext}"

    @staticmethod
    def generate_media_key(agent_id: str | uuid.UUID, media_type: str, filename: str) -> str:
        """Generate a unique S3 key for media files."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        unique_id = uuid.uuid4().hex[:12]
        return f"agents/{agent_id}/media/{media_type}/{unique_id}.{ext}"
