from prometheus_client import Counter, Gauge, Histogram

# Data update metrics
data_update_total = Counter(
    'opal_data_update_total', 'Total number of data update events published'
)

data_update_errors = Counter(
    'opal_data_update_errors', 'Total number of errors in data update publishing'
)

data_update_count_per_topic = Counter(
    'opal_data_update_count_per_topic',
    'Count of data updates published per topic',
    labelnames=['topic']
)

# Policy update metrics
policy_update_count = Counter(
    'opal_policy_update_count',
    'Total number of policy updates triggered',
    labelnames=['source']
)

policy_update_latency = Histogram(
    'opal_policy_update_latency_seconds',
    'Latency of policy bundle generation in seconds',
    labelnames=['source']
)

policy_bundle_request_count = Counter(
    'opal_policy_bundle_request_count',
    'Total number of policy bundle requests'
)

policy_bundle_latency = Histogram(
    'opal_policy_bundle_latency_seconds',
    'Latency of serving policy bundles in seconds'
)

policy_update_size = Histogram(
    'opal_policy_update_size',
    'Size of policy updates (in number of files)',
    buckets=[1, 10, 50, 100, 500, 1000]
)