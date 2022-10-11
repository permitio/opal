from typing import Optional

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


def init_data_updates_router(
    data_update_publisher: DataUpdatePublisher,
    data_sources_config: ServerDataSourceConfig,
    authenticator: JWTAuthenticator,
):
    router = APIRouter()

    @router.get(opal_server_config.ALL_DATA_ROUTE)
    async def default_all_data():
        """A fake data source configured to be fetched by the default data
        source config.

        If the user deploying OPAL did not set DATA_CONFIG_SOURCES
        properly, OPAL clients will be hitting this route, which will
        return an empty dataset (empty dict).
        """
        logger.warning(
            "Serving default all-data route, meaning DATA_CONFIG_SOURCES was not configured!"
        )
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

        data_update_publisher.publish_data_updates(update)
        return {"status": "ok"}

    return router
