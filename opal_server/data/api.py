from fastapi import APIRouter

from opal_common.logger import logger
from opal_common.schemas.data import DataUpdate
from opal_server.config import DataSourceConfig, opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher


def init_data_updates_router(data_update_publisher: DataUpdatePublisher, data_sources_config: DataSourceConfig):
    router = APIRouter()

    @router.get(opal_server_config.ALL_DATA_ROUTE)
    async def default_all_data():
        logger.warning("Serving default all-data route, meaning DATA_CONFIG_SOURCES was not configured!")
        return {}

    @router.get(opal_server_config.DATA_CONFIG_ROUTE)
    async def get_default_data_config():
        logger.info("Serving source configuration")
        return data_sources_config


    @router.post(opal_server_config.DATA_CONFIG_ROUTE)
    async def publish_data_update_event(update:DataUpdate):
        logger.info("Publishing received update event")
        data_update_publisher.publish_data_updates(update)
        return {"status": "ok"}

    return router

