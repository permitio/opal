import asyncio
import os
from typing import List

from fastapi_utils.tasks import repeat_every
from opal_common.logger import logger
from opal_common.schemas.data import (
    DataSourceEntryWithPollingInterval,
    DataUpdate,
    ServerDataSourceConfig,
)
from opal_common.topics.publisher import TopicPublisher

TOPIC_DELIMITER = "/"
PREFIX_DELIMITER = ":"


class DataUpdatePublisher:
    def __init__(self, publisher: TopicPublisher) -> None:
        self._publisher = publisher

    @staticmethod
    def get_topic_combos(topic: str) -> List[str]:
        """Get the The combinations of sub topics for the given topic e.g.
        "policy_data/users/keys" -> ["policy_data", "policy_data/users",
        "policy_data/users/keys"]

        If a colon (':') is present, only split after the right-most one,
        and prepend the prefix before it to every topic, e.g.
        "data:policy_data/users/keys" -> ["data:policy_data", "data:policy_data/users",
        "data:policy_data/users/keys"]

        Args:
            topic (str): topic string with sub topics delimited by delimiter

        Returns:
            List[str]: The combinations of sub topics for the given topic
        """
        topic_combos = []

        prefix = None
        if PREFIX_DELIMITER in topic:
            prefix, topic = topic.rsplit(":", 1)

        sub_topics = topic.split(TOPIC_DELIMITER)

        if sub_topics:
            current_topic = sub_topics[0]

            if prefix:
                topic_combos.append(f"{prefix}{PREFIX_DELIMITER}{current_topic}")
            else:
                topic_combos.append(current_topic)
            if len(sub_topics) > 1:
                for sub in sub_topics[1:]:
                    current_topic = f"{current_topic}{TOPIC_DELIMITER}{sub}"
                    if prefix:
                        topic_combos.append(
                            f"{prefix}{PREFIX_DELIMITER}{current_topic}"
                        )
                    else:
                        topic_combos.append(current_topic)

        return topic_combos

    def publish_data_updates(self, update: DataUpdate):
        """Notify OPAL subscribers of a new data update by topic.

        Args:
            topics (List[str]): topics (with hierarchy) to notify subscribers of
            update (DataUpdate): update data-source configuration for subscribers to fetch data from
        """
        all_topic_combos = []

        # Expand the topics for each event to include sub topic combos (e.g. publish 'a/b/c' as 'a' , 'a/b', and 'a/b/c')
        for entry in update.entries:
            for topic in entry.topics:
                topic_combos = DataUpdatePublisher.get_topic_combos(topic)
                all_topic_combos.extend(topic_combos)

        # a nicer format of entries to the log
        logged_entries = [
            dict(
                url=entry.url,
                method=entry.save_method,
                path=entry.dst_path or "/",
                inline_data=(entry.data is not None),
            )
            for entry in update.entries
        ]

        # publish all topics with all their sub combinations
        logger.info(
            "[{pid}] Publishing data update to topics: {topics}, reason: {reason}, entries: {entries}",
            pid=os.getpid(),
            topics=all_topic_combos,
            reason=update.reason,
            entries=logged_entries,
        )
        self._publisher.publish(all_topic_combos, update)

    async def _periodic_update_callback(
        self, update: DataSourceEntryWithPollingInterval
    ):
        """Called for every periodic update based on repeat_every."""
        logger.info(
            "[{pid}] Sending Periodic update: {source}", pid=os.getpid(), source=update
        )
        # Create new publish entry

        return self.publish_data_updates(
            DataUpdate(reason="Periodic Update", entries=[update])
        )

    def create_polling_updates(self, sources: ServerDataSourceConfig):
        # For every entry with a non zero period update interval, bind an inverval to it
        updaters = []
        if hasattr(sources, "config") and hasattr(sources.config, "entries"):
            for source in sources.config.entries:
                if (
                    hasattr(source, "periodic_update_interval")
                    and isinstance(source.periodic_update_interval, float)
                    and source.periodic_update_interval is not None
                ):
                    logger.info(
                        "[{pid}] Establishing Period Updates for the following source: {source}",
                        pid=os.getpid(),
                        source=source,
                    )

                    async def bind_for_repeat():
                        await self._periodic_update_callback(source)

                    updaters.append(
                        repeat_every(
                            seconds=source.periodic_update_interval,
                            wait_first=True,
                            logger=logger,
                        )(bind_for_repeat)
                    )
        return updaters

    @staticmethod
    async def mount_and_start_polling_updates(
        publisher: TopicPublisher, sources: ServerDataSourceConfig
    ):
        logger.info("[{pid}] Starting Polling Updates", pid=os.getpid())
        data_publisher = DataUpdatePublisher(publisher)
        await asyncio.gather(
            *(
                polling_update()
                for polling_update in data_publisher.create_polling_updates(sources)
            )
        )
