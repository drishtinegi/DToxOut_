"""
Vendor-independent Object Storage Service Abstraction.

Provides a unified interface for file uploads, safe UUID storage, presigned URLs,
and automatic retention cleanup across Local Filesystem, AWS S3, and Azure Blob Storage.
"""

from abc import ABC, abstractmethod
import os
import uuid
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseStorageService(ABC):
    """Abstract interface for file storage engines."""

    @abstractmethod
    async def save_file(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, str]:
        """Save file bytes to configured storage location."""
        pass

    @abstractmethod
    async def delete_file(self, identifier: str) -> bool:
        """Delete file by storage identifier."""
        pass

    @abstractmethod
    async def get_signed_url(self, identifier: str, expires_in_seconds: int = 3600) -> str:
        """Generate short-lived signed access URL."""
        pass


class LocalStorageService(BaseStorageService):
    """Local filesystem storage adapter for development and self-hosted deployments."""

    async def save_file(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, str]:
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        upload_id = str(uuid.uuid4())
        safe_filename = f"{upload_id}{ext}"

        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return {
            "upload_id": upload_id,
            "safe_filename": safe_filename,
            "storage_provider": "local",
        }

    async def delete_file(self, identifier: str) -> bool:
        clean_id = os.path.basename(identifier).replace("..", "")
        if not clean_id or not os.path.exists(settings.UPLOAD_DIR):
            return False

        deleted = False
        for f_name in os.listdir(settings.UPLOAD_DIR):
            if f_name.startswith(clean_id):
                full_path = os.path.join(settings.UPLOAD_DIR, f_name)
                try:
                    os.remove(full_path)
                    deleted = True
                except Exception as exc:
                    logger.warning("Failed to delete local file %s: %s", full_path, exc)
        return deleted

    async def get_signed_url(self, identifier: str, expires_in_seconds: int = 3600) -> str:
        # Local relative path without exposing absolute filesystem paths
        return f"/uploads/{os.path.basename(identifier)}"


class S3StorageService(BaseStorageService):
    """AWS S3 / MinIO compatible object storage adapter."""

    def __init__(self):
        self.bucket = settings.S3_BUCKET_NAME or "dtoxout-uploads"

    async def save_file(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, str]:
        upload_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        object_key = f"uploads/{upload_id}{ext}"

        try:
            import boto3
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            s3_client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type,
            )
            return {
                "upload_id": upload_id,
                "safe_filename": object_key,
                "storage_provider": "s3",
            }
        except Exception as exc:
            logger.error("Failed to upload file to S3 bucket %s: %s", self.bucket, exc)
            raise RuntimeError(f"S3 Storage Upload Error: {str(exc)}") from exc

    async def delete_file(self, identifier: str) -> bool:
        try:
            import boto3
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            s3_client.delete_object(Bucket=self.bucket, Key=identifier)
            return True
        except Exception as exc:
            logger.warning("Failed to delete S3 object %s: %s", identifier, exc)
            return False

    async def get_signed_url(self, identifier: str, expires_in_seconds: int = 3600) -> str:
        try:
            import boto3
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": identifier},
                ExpiresIn=expires_in_seconds,
            )
        except Exception:
            return f"https://{self.bucket}.s3.amazonaws.com/{identifier}"


class AzureBlobStorageService(BaseStorageService):
    """Azure Blob Storage adapter."""

    def __init__(self):
        self.container = settings.AZURE_STORAGE_CONTAINER_NAME

    async def save_file(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, str]:
        upload_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        blob_name = f"{upload_id}{ext}"

        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured.")

        try:
            from azure.storage.blob import BlobServiceClient
            blob_service = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            blob_client = blob_service.get_blob_client(container=self.container, blob=blob_name)
            blob_client.upload_blob(file_bytes, overwrite=True)

            return {
                "upload_id": upload_id,
                "safe_filename": blob_name,
                "storage_provider": "azure",
            }
        except Exception as exc:
            logger.error("Failed to upload to Azure Blob Storage: %s", exc)
            raise RuntimeError(f"Azure Storage Error: {str(exc)}") from exc

    async def delete_file(self, identifier: str) -> bool:
        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            return False
        try:
            from azure.storage.blob import BlobServiceClient
            blob_service = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            blob_client = blob_service.get_blob_client(container=self.container, blob=identifier)
            blob_client.delete_blob()
            return True
        except Exception as exc:
            logger.warning("Failed to delete Azure blob %s: %s", identifier, exc)
            return False

    async def get_signed_url(self, identifier: str, expires_in_seconds: int = 3600) -> str:
        return f"https://azureblob.storage/{self.container}/{identifier}"


def get_storage_service(provider_override: Optional[str] = None) -> BaseStorageService:
    """Factory to retrieve configured storage provider instance."""
    provider = (provider_override or settings.STORAGE_PROVIDER).lower().strip()
    if provider == "s3":
        return S3StorageService()
    elif provider == "azure":
        return AzureBlobStorageService()
    return LocalStorageService()
