import base64
import glob
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from hashlib import sha1
from typing import Dict, List, Tuple

import aiohttp


def get_filepaths_with_glob(root_path: str, file_regex: str):
    return glob.glob(os.path.join(root_path, file_regex))


def hash_file(tmp_file_path):
    BUF_SIZE = 65536  # lets read stuff in 64kb chunks!
    sha256_hash = hashlib.sha256()
    with open(tmp_file_path, "rb") as file:
        while True:
            data = file.read(BUF_SIZE)
            if not data:
                break
            sha256_hash.update(data)
    return sha256_hash.hexdigest()


async def throw_if_bad_status_code(
    response: aiohttp.ClientResponse, expected: List[int], logger=None
) -> aiohttp.ClientResponse:
    if response.status in expected:
        return response

    # else, bad status code. The body is not necessarily JSON (e.g. an HTML 502
    # page from a proxy), and response.json() would raise ContentTypeError.
    body = await response.text(errors="replace")
    try:
        details = json.loads(body)
    except json.JSONDecodeError:
        details = body
    if logger:
        logger.warning(
            "Unexpected response code {status}: {details}",
            status=response.status,
            details=details,
        )
    raise ValueError(
        f"unexpected response code while fetching bundle: {response.status}"
    )


def tuple_to_dict(tup: Tuple[str, str]) -> Dict[str, str]:
    return dict([tup])


def get_authorization_header(token: str) -> Tuple[str, str]:
    return "Authorization", f"Bearer {token}"


def build_aws_rest_auth_headers(
    key_id: str, secret_key: str, host: str, path: str, region: str
):
    """Use the AWS signature algorithm (https://docs.aws.amazon.com/AmazonS3/la
    test/userguide/RESTAuthentication.html) to generate the hTTP headers.

    Args:
        key_id (str): Access key (aka user ID) of an account in the S3 service.
        secret_key (str): Secret key (aka password) of an account in the S3 service.
        host (str): S3 storage host
        path (str): path to bundle file in s3 storage (including bucket)

    Returns: http headers
    """

    def sign(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def getSignatureKey(key, dateStamp, regionName, serviceName):
        kDate = sign(("AWS4" + key).encode("utf-8"), dateStamp)
        kRegion = sign(kDate, regionName)
        kService = sign(kRegion, serviceName)
        kSigning = sign(kService, "aws4_request")
        return kSigning

    # SHA256 of empty string.  This is needed when S3 request payload is empty.
    SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    t = datetime.now(timezone.utc)
    amzdate = t.strftime("%Y%m%dT%H%M%SZ")
    datestamp = t.strftime("%Y%m%d")

    canonical_headers = "host:" + host + "\n" + "x-amz-date:" + amzdate + "\n"
    signed_headers = "host;x-amz-date"

    payload_hash = hashlib.sha256("".encode("utf-8")).hexdigest()

    canonical_request = (
        "GET"
        + "\n"
        + path
        + "\n"
        + "\n"
        + canonical_headers
        + "\n"
        + signed_headers
        + "\n"
        + payload_hash
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = datestamp + "/" + region + "/" + "s3" + "/" + "aws4_request"

    string_to_sign = (
        algorithm
        + "\n"
        + amzdate
        + "\n"
        + credential_scope
        + "\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )
    signing_key = getSignatureKey(secret_key, datestamp, region, "s3")
    signature = hmac.new(
        signing_key, (string_to_sign).encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization_header = (
        algorithm
        + " "
        + "Credential="
        + key_id
        + "/"
        + credential_scope
        + ", "
        + "SignedHeaders="
        + signed_headers
        + ", "
        + "Signature="
        + signature
    )

    return {
        "x-amz-date": amzdate,
        "x-amz-content-sha256": SHA256_EMPTY,
        "Authorization": authorization_header,
    }


def sorted_list_from_set(s: set) -> list:
    l = list(s)
    l.sort()
    return l
