from dataclasses import dataclass
import boto3

from mcsg.storage import RemoteStorage, FileInfo

@dataclass
class S3Config:
    bucket_name: str
    region_name: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str
    region_name: str

class S3Storage(RemoteStorage):
    def __init__(self, storage_config: S3Config):
        self.bucket_name = storage_config.bucket_name
        self.s3 = boto3.client("s3",
            endpoint_url=storage_config.endpoint_url,
            region_name=storage_config.region_name,
            aws_access_key_id=storage_config.access_key_id,
            aws_secret_access_key=storage_config.secret_access_key
        )

    def store(self, local_path: str, remote_path: str):
        self.s3.upload_file(local_path, self.bucket_name, remote_path)

    def retrieve(self, remote_path: str, local_path: str):
        self.s3.download_file(self.bucket_name, remote_path, local_path)

    def delete(self, remote_path: str):
        self.s3.delete_object(Bucket=self.bucket_name, Key=remote_path)

    def list(self, remote_path: str):
        response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=remote_path)
        return [FileInfo(
            path=obj["Key"],
            filename=obj["Key"].split("/")[-1],
            size=obj["Size"],
            updated_at=obj["LastModified"],
            hash=obj["ETag"]
        ) for obj in response.get("Contents", [])]

    def join_path(self, *paths: str):
        return "/".join(paths)