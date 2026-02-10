"""
Management command to setup S3/RustyFS buckets.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import boto3
from botocore.exceptions import ClientError


class Command(BaseCommand):
    help = 'Setup S3/RustyFS buckets for data lake'
    
    def handle(self, *args, **options):
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        
        bucket_name = settings.DATA_LAKE_BUCKET
        
        # Create bucket
        try:
            s3_client.create_bucket(Bucket=bucket_name)
            self.stdout.write(
                self.style.SUCCESS(f'✓ Created bucket: {bucket_name}')
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                self.stdout.write(
                    self.style.WARNING(f'Bucket already exists: {bucket_name}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Error creating bucket: {e}')
                )
                return
        
        # Create folder structure
        folders = [
            'raw/uploads/',
            'raw/external/',
            'processed/flows/',
            'processed/aggregates/',
            'results/reports/',
            'results/exports/',
        ]
        
        for folder in folders:
            try:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=folder,
                    Body=b''
                )
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created folder: {folder}')
                )
            except ClientError as e:
                self.stdout.write(
                    self.style.ERROR(f'Error creating folder {folder}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ S3 bucket setup complete!')
        )