from prometheus_client import Counter, Gauge, Histogram

data_update_total = Counter(
    'opal_data_update_total', 'Total number of data update events published'
)

data_update_errors = Counter(
    'opal_data_update_errors', 'Total number of errors in data update publishing'
)

data_update_latency = Histogram(
    'opal_data_update_latency_seconds', 'Latency of data update events in seconds'
)