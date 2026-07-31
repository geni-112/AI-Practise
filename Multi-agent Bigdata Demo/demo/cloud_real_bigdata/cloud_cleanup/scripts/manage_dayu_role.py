"""Manage the temporary DAYU Administrator role used by the cleanup function."""

from __future__ import annotations

import argparse
import os

from huaweicloudsdkcore.auth.credentials import GlobalCredentials
from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkiam.v3 import (
    AssociateAgencyWithProjectPermissionRequest,
    CheckProjectPermissionForAgencyRequest,
    IamClient,
    RemoveProjectPermissionFromAgencyRequest,
)
from huaweicloudsdkiam.v3.region.iam_region import IamRegion


DEFAULT_AGENCY_ID = "0cb9cfc3ac00106c4f2fc007d0d69466"
DAYU_ADMIN_ROLE_ID = "7fc500135f3d4e44aa8fbd2f51911ec6"


def build_client(region: str) -> IamClient:
    credentials = GlobalCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
    )
    return (
        IamClient.new_builder()
        .with_credentials(credentials)
        .with_region(IamRegion.value_of(region))
        .build()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("attach", "check", "remove"))
    parser.add_argument("--agency-id", default=DEFAULT_AGENCY_ID)
    parser.add_argument("--role-id", default=DAYU_ADMIN_ROLE_ID)
    args = parser.parse_args()

    region = os.environ.get("HUAWEICLOUD_REGION", "la-south-2")
    project_id = os.environ["HUAWEICLOUD_PROJECT_ID"]
    client = build_client(region)
    request_args = {
        "project_id": project_id,
        "agency_id": args.agency_id,
        "role_id": args.role_id,
    }

    try:
        if args.action == "attach":
            response = client.associate_agency_with_project_permission(
                AssociateAgencyWithProjectPermissionRequest(**request_args)
            )
            print(f"DAYU Administrator role attached; HTTP {response.status_code}.")
        elif args.action == "remove":
            response = client.remove_project_permission_from_agency(
                RemoveProjectPermissionFromAgencyRequest(**request_args)
            )
            print(f"DAYU Administrator role removed; HTTP {response.status_code}.")
        else:
            response = client.check_project_permission_for_agency(
                CheckProjectPermissionForAgencyRequest(**request_args)
            )
            print(f"DAYU Administrator role is attached; HTTP {response.status_code}.")
    except exceptions.ClientRequestException as error:
        if args.action in ("check", "remove") and error.status_code == 404:
            print("DAYU Administrator role is not attached.")
            return 0
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
