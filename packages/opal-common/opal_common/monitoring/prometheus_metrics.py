from prometheus_client import Counter, Gauge, Histogram

# Opal Server Data update metrics
opal_server_data_update_total = Counter(
    'opal_server_data_update_total',
    'Total number of data update events published to opal server',
    ["status", "type"]
)

opal_server_data_update_errors = Counter(
    'opal_server_data_update_errors',
    'Total number of errors in opal server data update publishing',
    ["error_type", "endpoint"]
)

opal_server_data_update_latency = Histogram(
    'opal_opal_server_data_update_latency_seconds',
    'Latency of data update publishing to opal server in seconds',
    buckets=[.001, .005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

opal_server_data_update_count_per_topic = Counter(
    'opal_server_data_update_count_per_topic',
    'Count of data updates published per topic to opal server',
    ['topic']
)

# Opal Server Policy update metrics
opal_server_policy_update_count = Counter(
    'pal_server_policy_update_count',
    'Total number of policy updates triggered to opal server',
    ["source", "status"]
)

opal_server_policy_update_latency = Histogram(
    'opal_server_policy_update_latency_seconds',
    'Latency of policy bundle generation in seconds',
    ["source", "status"],
    buckets=[.01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

opal_server_policy_bundle_request_count = Counter(
    'opal_server_policy_bundle_request_count',
    'Total number of policy bundle requests',
    ["type"]
)

opal_server_policy_bundle_latency = Histogram(
    'opal_server_policy_bundle_latency_seconds',
    'Latency of serving policy bundles in seconds',
    ["type"],
    buckets=[.01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

opal_server_policy_update_size = Histogram(
    'opal_server_policy_update_size',
    'Size of policy updates (in number of files)',
    ["type"],
    buckets=[1, 10, 50, 100, 500, 1000]
)

# Scope metrics
opal_server_scope_request_count = Counter(
    'opal_server_scope_request_count',
    'Total number of requests to scope endpoints',
    ["endpoint", "method", "status"]
)

opal_server_scope_request_latency = Histogram(
    'opal_server_scope_request_latency',
    'Latency of scope requests in seconds',
    ["endpoint", "method", "status"],
    buckets=[.01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

opal_server_scope_data_update_count = Counter(
    'opal_server_scope_data_update_count',
    'Total number of data updates published per scope',
    labelnames=['scope_id']
)

opal_server_scope_data_update_errors = Counter(
    'opal_server_scope_data_update_errors',
    'Total number of errors during data update publication per scope',
    labelnames=['scope_id']
)

opal_server_scope_data_update_latency = Histogram(
    'opal_server_scope_data_update_latency_seconds',
    'Latency of data update publishing in seconds per scope',
    labelnames=['scope_id']
)

opal_server_scope_policy_sync_count = Counter(
    'opal_server_scope_policy_sync_count',
    'Total number of policy syncs per scope',
    labelnames=['scope_id']
)

opal_server_scope_policy_sync_latency = Histogram(
    'opal_server_scope_policy_sync_latency_seconds',
    'Latency of policy sync in seconds per scope',
    labelnames=['scope_id']
)

opal_server_scope_error_count = Counter(
    'opal_server_scope_error_count',
    'Total count of errors encountered per scope operation',
    ["scope_id", "error_type", "endpoint"]
)

opal_server_scope_operation_count = Counter(
    "opal_server_scope_operation_count",
    "Number of scope operations (create/update/delete)",
    ["operation", "status"]
)

# Generic metrics
token_request_count = Counter(
    "opal_token_request_count",
    "Total number of token requests",
    ["token_type", "status"]
)

token_generated_count = Counter(
    "opal_token_generated_count",
    "Number of successfully generated tokens",
    ["peer_type", "ttl"]
)

token_generation_errors = Counter(
    "opal_token_generation_errors",
    "Total number of errors during token generation",
    ["error_type", "token_type"]
)

# Client metrics
active_clients = Gauge(
    'opal_active_clients_total',
    'Number of currently connected OPAL clients',
    ['client_id', 'source']
)

client_data_subscriptions = Gauge(
    'opal_client_data_subscriptions',
    'Number of data topics a client is subscribed to',
    ['client_id', 'topic']
)

# Opal Client metrics
opal_client_data_update_trigger_count = Counter(
    'opal_client_data_update_trigger_count',
    'Number of data update triggers',
    ['source', 'status']
)

opal_client_data_update_latency = Histogram(
    'opal_client_data_update_latency_seconds',
    'Latency of data update operations',
    ['source'],
    buckets=[.01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

opal_client_data_update_errors = Counter(
    'opal_client_data_update_errors',
    'Number of errors during data updates',
    ['error_type', 'source']
)

opal_client_policy_update_trigger_count = Counter(
    'opal_client_policy_update_trigger_count',
    'Number of policy update triggers',
    ['source', 'status', 'update_type']
)

opal_client_policy_update_latency = Histogram(
    'opal_client_policy_update_latency_seconds',
    'Latency of policy update operations',
    ['source', 'update_type'],
    buckets=[.01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

opal_client_policy_update_errors = Counter(
    'opal_client_policy_update_errors',
    'Number of errors during policy updates',
    ['error_type', 'source']
)

opal_client_policy_store_request_count = Counter(
    'opal_client_policy_store_request_count',
    'Number of requests to policy store endpoints',
    ['endpoint', 'status']
)

opal_client_policy_store_request_latency = Histogram(
    'opal_client_policy_store_request_latency_seconds',
    'Latency of policy store requests',
    ['endpoint'],
    buckets=[.01, .025, .05, .075, .1, .25, .5, .75, 1.0]
)

opal_client_policy_store_auth_errors = Counter(
    'opal_client_policy_store_auth_errors',
    'Number of authentication/authorization errors for policy store',
    ['error_type', 'endpoint']
)

opal_client_policy_store_status = Gauge(
    'opal_client_policy_store_status',
    'Current status of policy store connection',
    ['auth_type']
)