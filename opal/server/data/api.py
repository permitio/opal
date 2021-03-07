from opal.common.schemas.data import DataUpdate
from opal.server.data.data_update_publisher import DataUpdatePublisher
from typing import List

from fastapi import APIRouter
from opal.common.logger import get_logger
from opal.server.config import DATA_CONFIG_ROUTE, DATA_CONFIG_SOURCES, DataSourceConfig



logger = get_logger('opal.server.data.api')


def init_data_updates_router(data_update_publisher: DataUpdatePublisher, data_sources_config: DataSourceConfig=None):
    if data_sources_config is None:
        data_sources_config = DATA_CONFIG_SOURCES
        
    router = APIRouter()

    @router.get(DATA_CONFIG_ROUTE)
    async def get_default_data_config():
        logger.info("Serving source configuration")
        return data_sources_config


    @router.post(DATA_CONFIG_ROUTE)
    async def publish_data_update_event(update:DataUpdate):
        logger.info("Publishing received update event")
        await data_update_publisher.publish_data_updates()

    return router

