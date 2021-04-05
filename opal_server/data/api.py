from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

from opal_common.logger import logger

from opal_common.schemas.data import DataSourceConfig, ServerDataSourceConfig, DataUpdate
from opal_server.config import opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher


def init_data_updates_router(data_update_publisher: DataUpdatePublisher, data_sources_config: ServerDataSourceConfig):
    router = APIRouter()

    @router.get(opal_server_config.ALL_DATA_ROUTE)
    async def default_all_data():
        logger.warning("Serving default all-data route, meaning DATA_CONFIG_SOURCES was not configured!")
        return {}

    @router.get(
        opal_server_config.DATA_CONFIG_ROUTE,
        response_model=DataSourceConfig,
        responses={
            307: {"description": "The data source configuration is available at another location (redirect)"},
        }
    )
    async def get_default_data_config():
        if data_sources_config.config is not None:
            logger.info("Serving source configuration")
            return data_sources_config.config
        elif data_sources_config.external_source_url is not None:
            url = str(data_sources_config.external_source_url)
            logger.info("Source configuration is available at '{url}', redirecting...", url=url)
            return RedirectResponse(url=url)
        else:
            logger.error("pydantic model invalid", model=data_sources_config)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Did not find a data source configuration!"
            )

    @router.post(opal_server_config.DATA_CONFIG_ROUTE)
    async def publish_data_update_event(update:DataUpdate):
        logger.info("Publishing received update event")
        data_update_publisher.publish_data_updates(update)
        return {"status": "ok"}

    return router

