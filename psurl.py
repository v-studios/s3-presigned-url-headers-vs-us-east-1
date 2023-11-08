#!/usr/bin/env python
import mimetypes
import os

import boto3  # I have boto3==1.28.79, Lambda has 1.27.1
import requests

REGION_BUCKETS = {
    "us-east-1": "psurlparis-dev-s3assets-121vx030ey5xk",
    "us-east-2": "psurlparis-dev-s3assets-1ukyhiu24hfzb",
    "eu-west-3": "psurlparis-dev-s3assets-rbwl0uyqt96g",
}


def get_psurl(region, bucket, filename):
    print(f"get_psurl: {region=} {bucket=}")

    mimetype = mimetypes.guess_type(filename)[0]

    s3c = boto3.client("s3", region_name=region)  # region overrides AWS_PROFILE
    metadata = {
        # If I put anything in Metadata, upload fails in all but us-east-1.
        # To fix, the PUT must include these headers with x-amz-meta-KEY: VALUE
        "filename": filename,
        "Content-Disposition": f"attachment; filename={filename}",
    }
    url = s3c.generate_presigned_url(
        ClientMethod="put_object",
        ExpiresIn=3600,
        HttpMethod="PUT",
        Params={
            "Bucket": bucket,
            "Key": filename,
            "ContentType": mimetype,
            "Metadata": metadata,
        }
    )
    headers = {f"x-amz-meta-{k.lower()}": v for k, v in metadata.items()}
    headers.update({"Content-Type": mimetype})
    return {
        "Bucket": bucket,
        "Filename": filename,
        "Headers": headers,
        "URL": url,
    }


def put_file(filename, headers, put_url):
    print(f"Uploading {filename=} {headers=} {put_url[:99]}")
    with open(filename, "rb") as upload_file:
        content = upload_file.read()
        headers = headers
        res = requests.put(put_url, data=content, headers=headers)
        return res


if __name__ == "__main__":
    """Test locally: create presigned URL, upload file to it.

    We use local creds from AWS_PROFILE when creating the URL.
    To prove the PSURL works, we remvoe the AWS_PROFILE when uploading.
    """
    for region, bucket in REGION_BUCKETS.items():
        filename = "fire.png"
        bucket = REGION_BUCKETS[region]
        res = get_psurl(region=region, bucket=bucket, filename=filename)

        put_url = res["URL"]
        headers = res["Headers"]
        print(f"{headers=} {put_url[:99]=}")

        aws_profile = os.environ["AWS_PROFILE"]
        del os.environ["AWS_PROFILE"]
        res = put_file(filename=filename, headers=headers, put_url=put_url)
        print(f"{res.status_code=} {res.reason=}")
        if res.status_code != 200:
            print(f"ERROR {res.content[:90]}")
        os.environ["AWS_PROFILE"] = aws_profile
        print()
