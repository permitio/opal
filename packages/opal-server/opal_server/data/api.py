import json
import os
from pathlib import Path
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from opal_common.authentication.authz import (
    require_peer_type,
    restrict_optional_topics_to_publish,
)
from opal_common.authentication.deps import JWTAuthenticator, get_token_from_header
from opal_common.authentication.types import JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.logger import logger
from opal_common.schemas.data import (
    DataSourceConfig,
    DataUpdate,
    DataUpdateReport,
    ServerDataSourceConfig,
)
from opal_common.schemas.security import PeerType
from opal_common.urls import set_url_query_param
from opal_server.config import opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher


def find_data_file(clone_path: str, data_filename: str) -> Optional[Path]:
    """Find the data file in the repository clone directory. First checks root
    directory, then searches subdirectories.

    Args:
        clone_path: Base directory to search
        data_filename: Name of file to find

    Returns:
        Path to data file if found, None otherwise
    """
    # First check root directory
    data_file = Path(clone_path) / data_filename
    if data_file.exists():
        logger.info(f"Found {data_filename} in root directory at {data_file}")
        return data_file

    # If not in root, search subdirectories
    for root, _, files in os.walk(clone_path):
        if data_filename in files:
            data_file = Path(root) / data_filename
            logger.info(f"Found {data_filename} in subdirectory at {data_file}")
            return data_file

    logger.warning(
        "No {filename} found in repository clone directory: {clone_path}",
        filename=data_filename,
        clone_path=clone_path,
    )
    return None


def load_json_data(file_path: Path) -> Tuple[Optional[dict], Optional[str]]:
    """Load and validate JSON data from a file.

    Args:
        file_path: Path to JSON file

    Returns:
        Tuple of (data dict, error message)
        If successful, error will be None
        If failed, data will be None and error will contain message
    """
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        if not data:  # Validate we got actual data
            return None, "File contained empty JSON object/array"
        logger.info(f"Successfully loaded data from {file_path}")
        return data, None
    except json.JSONDecodeError:
        error = f"Invalid JSON format in {file_path}"
        logger.error(error)
        return None, error
    except Exception as e:
        error = f"Error reading {file_path}: {str(e)}"
        logger.error(error)
        return None, error


def init_data_updates_router(
    data_update_publisher: DataUpdatePublisher,
    data_sources_config: ServerDataSourceConfig,
    authenticator: JWTAuthenticator,
):
    router = APIRouter()

    @router.get(opal_server_config.ALL_DATA_ROUTE)
    async def default_all_data():
        """Look for default data file in the repo clone directory and return
        its contents."""
        try:
            clone_path = opal_server_config.POLICY_REPO_CLONE_PATH
            data_filename = opal_server_config.POLICY_REPO_DEFAULT_DATA_FILENAME

            # First find the data file
            data_file = find_data_file(clone_path, data_filename)
            if not data_file:
                return {}

            # Then load and validate its contents
            data, error = load_json_data(data_file)
            if error:
                logger.error(f"Error loading data file: {error}")
                return {}

            return data

        except Exception as e:
            logger.error(f"Error in default_all_data: {str(e)}")
            return {}

    @router.post(
        opal_server_config.DATA_CALLBACK_DEFAULT_ROUTE,
        dependencies=[Depends(authenticator)],
    )
    async def log_client_update_report(report: DataUpdateReport):
        """A data update callback to be called by the OPAL client after
        completing an update.

        If the user deploying OPAL-client did not set
        OPAL_DEFAULT_UPDATE_CALLBACKS properly, this method will be
        called as the default callback (will simply log the report).
        """
        logger.info(
            "Received update report: {report}",
            report=report.dict(
                exclude={"reports": {"__all__": {"entry": {"config", "data"}}}}
            ),
        )
        return {}  # simply returns 200

    @router.get(
        opal_server_config.DATA_CONFIG_ROUTE,
        response_model=DataSourceConfig,
        responses={
            307: {
                "description": "The data source configuration is available at another location (redirect)"
            },
        },
        dependencies=[Depends(authenticator)],
    )
    async def get_data_sources_config(authorization: Optional[str] = Header(None)):
        """Provides OPAL clients with their base data config, meaning from
        where they should fetch a *complete* picture of the policy data they
        need.

        Clients will use this config to pull all data when they
        initially load and when they are reconnected to server after a
        period of disconnection (in which they cannot receive
        incremental updates).
        """
        token = get_token_from_header(authorization)
        if data_sources_config.config is not None:
            logger.info("Serving source configuration")
            return data_sources_config.config
        elif data_sources_config.external_source_url is not None:
            url = str(data_sources_config.external_source_url)
            short_token = token[:5] + "..." + token[-5:]
            logger.info(
                "Source configuration is available at '{url}', redirecting with token={token} (abbrv.)",
                url=url,
                token=short_token,
            )
            redirect_url = set_url_query_param(url, "token", token)
            return RedirectResponse(url=redirect_url)
        else:
            logger.error("pydantic model invalid", model=data_sources_config)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Did not find a data source configuration!",
            )

    @router.post(opal_server_config.DATA_CONFIG_ROUTE)
    async def publish_data_update_event(
        update: DataUpdate, claims: JWTClaims = Depends(authenticator)
    ):
        """Provides data providers (i.e: one of the backend services owned by
        whomever deployed OPAL) with the ability to push incremental policy
        data updates to OPAL clients.

        Each update contains instructions on:
        - how to fetch the data
        - where should OPAL client store the data in OPA document hierarchy
        - what clients should receive the update (through topics, only clients subscribed to provided topics will be notified)
        """
        try:
            require_peer_type(
                authenticator, claims, PeerType.datasource
            )  # may throw Unauthorized
            restrict_optional_topics_to_publish(
                authenticator, claims, update
            )  # may throw Unauthorized
        except Unauthorized as e:
            logger.error(f"Unauthorized to publish update: {repr(e)}")
            raise

        await data_update_publisher.publish_data_updates(update)
        return {"status": "ok"}

    return router
