package system.opal

# -----------------------------------------------------------------------------------
# Ready rule - opal successfully loaded at least one policy bundle and data update
# -----------------------------------------------------------------------------------
default ready = {ready}

# -----------------------------------------------------------------------------------
# Healthy rule - the last policy-write and data-write transactions were successful.
#
# Note:
# At the moment we make an (inaccurate but simplified) assumption that successful
# transactions reset the bad state (going out of sync) caused by failed transactions.
# -----------------------------------------------------------------------------------
default healthy = {healthy}

last_policy_transaction := {last_policy_transaction}
last_data_transaction := {last_data_transaction}
last_failed_policy_transaction := {last_failed_policy_transaction}
last_failed_data_transaction := {last_failed_data_transaction}

transaction_data_statistics := {transaction_data_statistics}
transaction_policy_statistics := {transaction_policy_statistics}
