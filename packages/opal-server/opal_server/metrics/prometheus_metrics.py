from prometheus_client import Counter, Gauge, Histogram

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