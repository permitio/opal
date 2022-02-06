# Run OPAL-server with a Kafka backbone pub/sub

## Introduction

#### What do we mean by backbone pub/sub or Broadcast-channel ?

OPAL-server can scale-out both in number of worker processes per server and in multiple servers.
While OPAL provides a lightweight websocket pub/sub for OPAL-clients, the multiple servers are linked together by a more heavyweight messaging solution - e.g. Kafka, Redis, or Postgres Listen/Notify.

#### Broadcaster module

Support for multiple backbone is provided by the [Python Broadcaster package](https://pypi.org/project/broadcaster/).
To use it with Kafka we need to install the `broadcaster[kafka]` module - with:
`pip install broadcaster[kafka]`

## Running with Kafka

When you run the OPAL-server you can choose which backend it should use with the `OPAL_BROADCAST_URI` option default is Postgres but running with Kafka is as simple as `OPAL_BROADCAST_URI=kafka://kafka-host-name:9092`
notice the "kafka://" prefix, that's how we tell OPAL-server to use Kafka.

#### Setting a Kafka topic (aka Backbone channel)

Be sure to configure the topic in your Kafka server that will act as a channel between all servers - the default name for it is `EventNotifier`.
But (in version OPAL 0.1.21 and later) you can also use the `OPAL_BROADCAST_CHANNEL` option to specify the name of the channel.

- Don't confuse the Kafka topic with the OPAL-server topics.
  - a Kafka topic is used to control which servers share clients and events.
  - OPAL topics control which clients receive which policy or data events.

## Docker-compose Example

Checkout `docker/docker-compose-with-kafka-example.yml` and the matching `docker/opal-server-with-kafka.dockerfile` for running docker compose with OPAL-server, OPAL-client, Zookeeper, and Kafka.

You'll need to run it with `docker-compose build` to create which will use the dockerfile to build an image of OPAL-server with the Kafka module.
e.g. when in the repository root run -

```
docker-compose -f ./docker/docker-compose-with-kafka-example.yml build
docker-compose -f ./docker/docker-compose-with-kafka-example.yml up
```

Give KafKa a few seconds to start up and then run and event update ([see triggering updates](https://github.com/permitio/opal/blob/master/docs/HOWTO/get_started_with_opal_docker_compose_tutorial.md#step-4-publish-a-data-update-via-the-opal-server)) to check for connectivity.

for example run an update with the OPAL cli:

```
opal-client publish-data-update --src-url https://api.country.is/23.54.6.78 -t policy_data --dst-path /users/bob/location
```

You should see the effect in:

- OPAL-server - you should see "Broadcasting incoming event" in the logs
- OPAL-client - should receive and act on the event
- Kafka - should see the event and it's data in the topic
  something like:
  ```Key: null
  Partition: 0
  Offset: 3
  Headers:
  Value:
  {"notifier_id": "9a9a97df1da64486a1a56a070f1c3db3", "topics": ["policy_data"], "data": {"id": null, "entries": [{"url": "https://api.country.is/23.54.6.78", "config": {}, "topics": ["policy_data"], "dst_path": "/users/bob/location", "save_method": "PUT"}], "reason": "", "callback": {"callbacks": []}}}
  ```

## Triggering events directly from Kafka

OPAL-server has a specific Schema for backbone events - [BroadcastNotification](https://github.com/authorizon/fastapi_websocket_pubsub/blob/3b567bb0f34e42c5e1162ffeae8d8c1d4eed43dc/fastapi_websocket_pubsub/event_broadcaster.py#L18) by writing JSON objects in the schema to the shared Kafka topic we can trigger events directly from Kafka.

## Schema

## Structure

- 'notifier_id': A random UUID identifying the source of the message (e.g. the OPAL-server sending it)- you can just make up one.

- data the event content of type [DataUpdate](https://github.com/permitio/opal/blob/
  8e1e63d585999902b9882633369cba5dcfe7ad3f/opal_common/schemas/data.py#L80) - 'id': UUID for the event itself (random / can be null) - 'reason': A human readable reason for the event (optional) - 'entires': a list of [DataSourceEntry](https://github.com/permitio/opal/blob/8e1e63d585999902b9882633369cba5dcfe7ad3f/opal_common/schemas/data.py#L9) - 'url': the url the clients should connect to in-order to get the data - 'config': the configuration for the data fetcher source (any object, optional) - 'topics': A list of OPAL topics to which the message is to be sent (for clients). - 'dst_path': [The path in OPA](https://www.openpolicyagent.org/docs/latest/rest-api/#data-api) to which the data should be saved. - 'save_method': The HTTP method to use when saving the data in OPA (PUT/ PATCH)

      - 'callback': an [UpdateCallback](https://github.com/permitio/opal/blob/8e1e63d585999902b9882633369cba5dcfe7ad3f/opal_common/schemas/data.py#L71) - Configuration for how to notify other services on the status of Update

## example object

```
{"notifier_id": "9a9a97df1da64486a1a56a070f1c3db3", "topics": ["policy_data"], "data": {"id": null, "entries": [{"url": "https://api.country.is/23.54.6.78", "config": {}, "topics": ["policy_data"], "dst_path": "/users/bob/location", "save_method": "PUT"}], "reason": "User reconnected from new IP", "callback": {"callbacks": []}}}
```
