===========================================================
Presigned URL Uploads vs HTTP Headers: us-east-1 is special
===========================================================

TL;DR:
======

To create a presigned URL, we have to provide matching headers in the
HTTP upload -- but us-east-1 doesn't require all of them, while other
regions do.

I Usually Deploy to us-east-1
=============================

I've done most of my development in us-east-1 since I lived in
Northern Virginia and worked in the area; heck, I've probably ridden
past one of the unlabeled AWS datacenters along the W & OD bike tail
in Loudon County.

Our work for a certain US space agency hosted most most of our compute
in us-east-1. We've done lots of apps that use presigned URLs to
upload to S3, and they've worked fine.

New Region, New Problems
========================

Until recently, I hadn't deployed to other regions (besides GovCloud).
I now live in Spain and want to deploy to a closer region -- Paris
seemed proximate. So I configured my Serverless Framework to use
eu-west-3, and it deployed fine there. But the presigned URLs broke:
exact same code, just a different region. I then tried us-east-2
(Ohio), and had the same failures. It seems us-east-1 is "special",
which is not good.

Python app, Distilled for Debugging
===================================

My app's using Python and the boto3 library. I went down a rat-hole
with S3 client specification and Configuration, and Signature methods
to no avail. I also read that newly-created S3 buckets take a while to
propagate their DNS names, and I've seen this when I tried to PUT and
got an HTTP Temporary Redirect from S3: changing the URL would surely
invalidate the signature. But these turned out not to be the problem
either.

My real app's code runs in a Lambda where the Execution Role gives it
permission to upload to S3. To debug the problem I extracted the main
presigned URL upload logic here so I can run it locally.

I want to be able to accept an HTTP ``Content-Type`` and
``Content-Disposition`` on upload so downloads will be named properly;
I also want to store the uploaded file's name in the S3 object
metadata, and perhaps other info like the file's owner. The `boto3
docs for put_object
<https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html#>`_
suggest that many headers may be sent to configure the uploaded
object, like ``ContentType``, ``ContentDispostion`` that we use here.
This `AWS re:post
<https://repost.aws/questions/QUgivVIUn6QrGVpETR1wQ4KQ/s3-sha256-checksum-for-presigned-url-in-file-upload#ANlT4L2fXZSe2H3Ezr5DNyZQ>`_
mentions them but not their provenance. I have not found a definitive
list of similar values I can provide to ``Params`` in
``generate_presigned_url()``.

Headers
=======

As I said, I started working in us-east-1. My client app (and curl) set the
HTTP ``Content-Type`` header upon upload to the presigned URL, so I
was obliged to include those in the presigned URL::

  def _get_presigned_url_put(bucket, key, filename, mimetype, expire_seconds):
      params = {
          "Bucket": bucket,
          "Key": key,
          "ContentType": mimetype,
          "Metadata": {"filename": filename,
                       "Content-Disposition": f"attachment; filename={filename}"},
      }
      url = S3C.generate_presigned_url(
          ClientMethod="put_object",
          ExpiresIn=expire_seconds,
          HttpMethod="PUT",
          Params=params,
      )
      return url

And this worked fine in us-east-1. But when I moved to app and bucket
in us-east-2 or eu-west-3, it failed. This was repeatable.

Headers Required in Most Regions
================================

I can set "system defined" characteristics of the file in the
presigned URL in ``Params``, and "user defined" attributes in
``Metadata``::

    content_disposition = f'attachment; filename="{filename}"'
    http_method = "PUT"
    mimetype = mimetypes.guess_type(filename)[0]
    metadata = {
        "filename": filename,
        "magic_words": "Squeamish Ossifrage",
    }
    s3c = boto3.client("s3", region_name=region)
    url = s3c.generate_presigned_url(
        ClientMethod="put_object",
        ExpiresIn=3600,
        HttpMethod=http_method,
        Params={
            "Bucket": bucket,
            "Key": filename,
            "ContentDisposition": content_disposition,
            "ContentType": mimetype,
            "Metadata": metadata,
        },
    )

The ``Params`` attributes (``ContentDisposition`` and
``ContentType``) had to be matched on the upload by properly-spelled
HTTP headers ``Content-Disposition`` and ``Content-Type``. The custom
settings in ``Metadata`` had to be matched with key-value pairs, where
the key names were downcased and prefixed by ``x-amz-meta-``::

    headers = {
        "Content-Type": mimetype,
        "Content-Disposition": content_disposition,
    }
    headers.update({f"x-amz-meta-{k.lower()}": v for k, v in metadata.items()})

Note that if I change the ``Params`` I'll need to update the
``headers`` to match, since they're spelled differently than the HTTP
header names.

To make it easier for the client uploader, I return not only the
presigned URL but also the headers it will need to supply, with the
right spelling for HTTP.


Verify us-east-1 is special, more promiscuous
=============================================

I use the `<serverless.yml>`_ file to define my infrastructure,
extracted from my larger app. I deploy three times, one for each
region in which I want an S3 bucket.

If we run the code, it tries the three identically-configured buckets
in three regions: us-east-1, us-east-2, eu-west-3. The upload succeeds
in each case.

But if we suppress the part where we add headers for the custom
``Metadata`` items::

    headers = {}
    # headers = {f"x-amz-meta-{k.lower()}": v for k, v in metadata.items()}

we see that us-east-1 is happy to accept the file, but the other
regions are not::

  ./psurl.py

  region='us-east-1' method='PUT'
  headers={'Content-Type': 'image/png', 'Content-Disposition': 'attachment; filename="fire.png"'}
  put_url[:90]='https://psurl-dev-s3assets-111savi37w6pt.s3.amazonaws.com/fire.png?AWSAccessKeyId=AKIASGHG'
  res.status_code=200 res.reason='OK'

  region='us-east-2' method='PUT'
  headers={'Content-Type': 'image/png', 'Content-Disposition': 'attachment; filename="fire.png"'}
  put_url[:90]='https://psurl-dev-s3assets-1btlz2jfl73sj.s3.amazonaws.com/fire.png?X-Amz-Algorithm=AWS4-HM'
  res.status_code=403 res.reason='Forbidden'
  ### ERROR b'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>SignatureDoesNotMatch</Code><Message>T'

  region='eu-west-3' method='PUT'
  headers={'Content-Type': 'image/png', 'Content-Disposition': 'attachment; filename="fire.png"'}
  put_url[:90]='https://psurl-dev-s3assets-19rz00qdke5v6.s3.amazonaws.com/fire.png?X-Amz-Algorithm=AWS4-HM'
  res.status_code=403 res.reason='Forbidden'
  ### ERROR b'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>SignatureDoesNotMatch</Code><Message>T'

Note that the URL for us-east-1 starts with ``AWSAccessKeyId`` while
the other regions' URL starts with ``X-Amz-Algorithm``. That's not what I'd
expect.

Restoring the ``headers`` for ``Metadata`` allows all regions to succeed again.

As usual, us-east-1 is a snowflake.
