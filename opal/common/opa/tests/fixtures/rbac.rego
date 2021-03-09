# Role-based Access Control (RBAC)
# --------------------------------
#
# This example defines an RBAC model for a Pet Store API. The Pet Store API allows
# users to look at pets, adopt them, update their stats, and so on. The policy
# controls which users can perform actions on which resources. The policy implements
# a classic Role-based Access Control model where users are assigned to roles and
# roles are granted the ability to perform some action(s) on some type of resource.
#
# This example shows how to:
#
#	* Define an RBAC model in Rego that interprets role mappings represented in JSON.
#	* Iterate/search across JSON data structures (e.g., role mappings)
#
# For more information see:
#
#	* Rego comparison to other systems: https://www.openpolicyagent.org/docs/latest/comparison-to-other-systems/
#	* Rego Iteration: https://www.openpolicyagent.org/docs/latest/#iteration

package app.rbac

# By default, deny requests.
default allow = false

# Allow admins to do anything.
allow {
	user_is_admin
}

# Allow the action if the user is granted permission to perform the action.
allow {
	# Find grants for the user.
	some grant
	user_is_granted[grant]

	# Check if the grant permits the action.
	input.action == grant.action
	input.type == grant.type
}

# user_is_admin is true if...
user_is_admin {

	# for some `i`...
	some i

	# "admin" is the `i`-th element in the user->role mappings for the identified user.
	data.user_roles[input.user][i] == "admin"
}

# user_is_granted is a set of grants for the user identified in the request.
# The `grant` will be contained if the set `user_is_granted` for every...
user_is_granted[grant] {
	some i, j

	# `role` assigned an element of the user_roles for this user...
	role := data.user_roles[input.user][i]

	# `grant` assigned a single grant from the grants list for 'role'...
	grant := data.role_grants[role][j]
}
