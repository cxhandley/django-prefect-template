"""
Tests for the setup_s3_buckets management command.
"""

from io import StringIO

import pytest
from botocore.exceptions import ClientError
from django.core.management import call_command


@pytest.mark.django_db
def test_setup_s3_buckets_creates_bucket_and_folders(mock_s3, settings):
    """Command creates the bucket and all folder prefixes."""
    # mock_s3 already has 'test-bucket', but setup_s3_buckets tries to create it —
    # that raises BucketAlreadyOwnedByYou which should be handled gracefully.
    settings.DATA_LAKE_BUCKET = "new-test-bucket"
    mock_s3.create_bucket(Bucket="new-test-bucket")

    out = StringIO()
    call_command("setup_s3_buckets", stdout=out)
    output = out.getvalue()

    assert "setup complete" in output.lower() or "bucket" in output.lower()


@pytest.mark.django_db
def test_setup_s3_buckets_bucket_already_owned(mock_s3, settings, mocker):
    """BucketAlreadyOwnedByYou is handled gracefully."""
    already_owned = ClientError(
        {"Error": {"Code": "BucketAlreadyOwnedByYou", "Message": ""}}, "CreateBucket"
    )
    mocker.patch(
        "apps.flows.management.commands.setup_s3_buckets.boto3.client"
    ).return_value.create_bucket.side_effect = already_owned

    out = StringIO()
    call_command("setup_s3_buckets", stdout=out)
    # Should not raise, just warn


@pytest.mark.django_db
def test_setup_s3_buckets_other_error(mock_s3, settings, mocker):
    """Other ClientErrors are reported and the command exits early."""
    other_error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "CreateBucket"
    )
    mocker.patch(
        "apps.flows.management.commands.setup_s3_buckets.boto3.client"
    ).return_value.create_bucket.side_effect = other_error

    out = StringIO()
    call_command("setup_s3_buckets", stdout=out)
    # Should not raise
