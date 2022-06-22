import os
from typing import List

from opal_common.logger import logger
from opal_common.schemas.data import DataUpdate
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
            (entry.url, entry.save_method, entry.dst_path or "/")
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
