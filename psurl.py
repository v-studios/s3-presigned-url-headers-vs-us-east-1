#!/usr/bin/env python
import mimetypes
import os

import boto3  # I have boto3==1.28.79, Lambda has 1.27.1
import requests

REGION_BUCKETS = {
    "us-east-1": "psurl-dev-s3assets-111savi37w6pt",
    "us-east-2": "psurl-dev-s3assets-1btlz2jfl73sj",
    #"eu-west-3": "psurl-dev-s3assets-19rz00qdke5v6",
}


def get_psurl(region, bucket, filename):
    """Generate a presigned URL to PUT a file to S3 bucket in a given region.

    Return the URL, HTTP method, and headers the uploader will need to send.
    """
    content_disposition = f'attachment; filename="{filename}"'
    http_method = "PUT"
    mimetype = mimetypes.guess_type(filename)[0]
    # If I put anything in Metadata, upload fails in regions *except* us-east-1;
    # to fix, the HTTP PUT must include these headers with x-amz-meta-KEY: VALUE
    metadata = {
        "filename": filename,
        "magic_words": "Squeamish Ossifrage",
        "Content-Disposition": content_disposition,
    }
    s3c = boto3.client("s3", region_name=region)  # region overrides AWS_PROFILE
    url = s3c.generate_presigned_url(
        ClientMethod="put_object",
        ExpiresIn=3600,
        HttpMethod=http_method,
        Params={
            "Bucket": bucket,
            "Key": filename,
            # These params must be matched in the PUT by HTTP-named headers
            "ContentType": mimetype,
            # Metadata items must be matched in the PUT by HTTP headers with prefix x-amz-meta-
            "Metadata": metadata,
        }
    )
    headers = {f"x-amz-meta-{k.lower()}": v for k, v in metadata.items()}
    # If we change the Parameters above we'll need to update these:
    headers.update({"Content-Type": mimetype})
    return {
        "Headers": headers,
        "Method": http_method,
        "URL": url,
    }


def put_file(filename, headers, put_url):
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

        method = res["Method"]
        headers = res["Headers"]
        put_url = res["URL"]
        print(f"{region=} {method=}\n{headers=}\n{put_url[:99]=}")

        aws_profile = os.environ["AWS_PROFILE"]
        del os.environ["AWS_PROFILE"]
        res = put_file(filename=filename, headers=headers, put_url=put_url)
        print(f"{res.status_code=} {res.reason=}")
        if res.status_code != 200:
            print(f"### ERROR {res.content[:90]}")
        os.environ["AWS_PROFILE"] = aws_profile
        print()
