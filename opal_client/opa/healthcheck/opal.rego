package system.opal

# Helper functions and rules --------------------------------------------------------
has_key(x, k) {
	_ = x[k]
}

# -----------------------------------------------------------------------------------
# Ready rule - opal successfully loaded at least one policy bundle and data update
# -----------------------------------------------------------------------------------
default ready = false

ready {
	successful_policy_transactions := [transaction |
		transaction := policy_transactions[_]
		transaction.success
	]

	successful_data_transactions := [transaction |
		transaction := data_transactions[_]
		transaction.success
	]

	count(successful_policy_transactions) > 0
	count(successful_data_transactions) > 0
}

# -----------------------------------------------------------------------------------
# Healthy rule - the last policy-write and data-write transactions were successful.
#
# Note:
# At the moment we make an (inaccurate but simplified) assumption that successful
# transactions reset the bad state (going out of sync) caused by failed transactions.
# -----------------------------------------------------------------------------------
default healthy = false

healthy {
	# makes sure at least one successful transaction of each type exists - precondition
	ready

	# we know there is at least one transaction in the array (otherwise not ready)
	# get the last transaction of each type
	last_policy_transaction := policy_transactions[count(policy_transactions)-1]
	last_data_transaction := data_transactions[count(data_transactions)-1]

	# make sure the last transaction of each type was successful
	last_policy_transaction.success
	last_data_transaction.success
}

# -----------------------------------------------------------------------------------
# (Public) Rules
# -----------------------------------------------------------------------------------
policy_transactions := [transaction |
	transaction := data.system.opal.transactions[_]
	policy_actions = ["set_policies", "set_policy", "delete_policy"]
	transaction.actions[_] == policy_actions[_]
]

data_transactions := [transaction |
	transaction := data.system.opal.transactions[_]
	data_actions = ["set_policy_data", "delete_policy_data"]
	transaction.actions[_] == data_actions[_]
]
