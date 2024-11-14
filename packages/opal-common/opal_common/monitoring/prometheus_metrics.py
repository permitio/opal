from prometheus_client import Counter, Gauge, Histogram

# Opal Server Data update metrics
opal_server_data_update_total = Counter(
    'opal_server_data_update_total', 'Total number of data update events published to opal server'
)

opal_server_data_update_errors = Counter(
    'opal_server_data_update_errors', 'Total number of errors in opal server data update publishing'
)

opal_server_data_update_latency = Histogram(
    'opal_opal_server_data_update_latency_seconds',
    'Latency of data update publishing to opal server in seconds'
)

opal_server_data_update_count_per_topic = Counter(
    'opal_server_data_update_count_per_topic',
    'Count of data updates published per topic to opal server',
    labelnames=['topic']
)

# Opal Server Policy update metrics
opal_server_policy_update_count = Counter(
    'pal_server_policy_update_count',
    'Total number of policy updates triggered to opal server',
    labelnames=['source']
)

opal_server_policy_update_latency = Histogram(
    'opal_server_policy_update_latency_seconds',
    'Latency of policy bundle generation in seconds',
    labelnames=['source']
)

opal_server_policy_bundle_request_count = Counter(
    'opal_server_policy_bundle_request_count',
    'Total number of policy bundle requests'
)

opal_server_policy_bundle_latency = Histogram(
    'opal_server_policy_bundle_latency_seconds',
    'Latency of serving policy bundles in seconds'
)

opal_server_policy_update_size = Histogram(
    'opal_server_policy_update_size',
    'Size of policy updates (in number of files)',
    buckets=[1, 10, 50, 100, 500, 1000]
)

# Scope metrics
opal_server_scope_request_count = Counter(
    'opal_server_scope_request_count',
    'Total number of requests to scope endpoints',
    labelnames=['endpoint', 'method']
)

opal_server_scope_request_latency = Histogram(
    'opal_server_scope_request_latency',
    'Latency of scope requests in seconds',
    labelnames=['endpoint', 'method']
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
    labelnames=['scope_id', 'error_type']
)

# Define metrics
token_request_count = Counter(
    "opal_token_request_count",
    "Total number of token requests",
)

token_generation_errors = Counter(
    "opal_token_generation_errors",
    "Total number of errors during token generation",
    labelnames=["error_type"]
)

token_generated_count = Counter(
    "opal_token_generated_count",
    "Total number of tokens successfully generated",
    labelnames=["peer_type"]
)