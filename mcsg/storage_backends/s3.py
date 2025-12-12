from dataclasses import dataclass
from typing import List
import boto3
from botocore.exceptions import ClientError

from mcsg.storage import RemoteStorage

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

    def store(self, local_path_list: List[str], remote_path_list: List[str]):
        for local_path, remote_path in zip(local_path_list, remote_path_list):
            self.s3.upload_file(local_path, self.bucket_name, remote_path)

    def retrieve(self, remote_path_list: List[str], local_path_list: List[str]):
        for remote_path, local_path in zip(remote_path_list, local_path_list):
            self.s3.download_file(self.bucket_name, remote_path, local_path)

    def delete(self, remote_path_list: List[str]):
        batch_size = 1000
        for i in range(0, len(remote_path_list), batch_size):
            self.s3.delete_objects(Bucket=self.bucket_name, Delete={"Objects": [{"Key": remote_path} for remote_path in remote_path_list[i:i+batch_size]]})

    def exists(self, remote_path: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=remote_path)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def list(self, remote_path: str) -> List[str]:
        response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=remote_path)
        return [obj["Key"] for obj in response["Contents"]]

    def join_path(self, *paths: str):
        return "/".join(paths)