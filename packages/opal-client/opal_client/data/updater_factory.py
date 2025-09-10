from typing import List, Optional

from fastapi_websocket_pubsub.pub_sub_client import PubSubOnConnectCallback
from fastapi_websocket_rpc.rpc_channel import OnDisconnectCallback
from opal_client.callbacks.register import CallbacksRegister
from opal_client.data.fetcher import DataFetcher
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_common.authentication.authenticator import Authenticator
from opal_common.config import opal_common_config
from opal_common.logger import logger

from .oauth2_updater import OAuth2DataUpdater
from .updater import DataUpdater, DefaultDataUpdater


class DataUpdaterFactory:
    @staticmethod
    def create(
        token: str = None,
        pubsub_url: str = None,
        data_sources_config_url: str = None,
        fetch_on_connect: bool = True,
        data_topics: List[str] = None,
        policy_store: BasePolicyStoreClient = None,
        should_send_reports=None,
        data_fetcher: Optional[DataFetcher] = None,
        callbacks_register: Optional[CallbacksRegister] = None,
        opal_client_id: str = None,
        shard_id: Optional[str] = None,
        on_connect: List[PubSubOnConnectCallback] = None,
        on_disconnect: List[OnDisconnectCallback] = None,
        authenticator: Optional[Authenticator] = None,
    ) -> DataUpdater:
        if opal_common_config.AUTH_TYPE == "oauth2":
            logger.info(
                "OPAL is running in secure mode - will authenticate Datasource requests with OAuth2 tokens."
            )
            return OAuth2DataUpdater(
                token,
                pubsub_url,
                data_sources_config_url,
                fetch_on_connect,
                data_topics,
                policy_store,
                should_send_reports,
                data_fetcher,
                callbacks_register,
                opal_client_id,
                shard_id,
                on_connect,
                on_disconnect,
                authenticator,
            )
        else:
            return DefaultDataUpdater(
                token,
                pubsub_url,
                data_sources_config_url,
                fetch_on_connect,
                data_topics,
                policy_store,
                should_send_reports,
                data_fetcher,
                callbacks_register,
                opal_client_id,
                shard_id,
                on_connect,
                on_disconnect,
                authenticator,
            )
