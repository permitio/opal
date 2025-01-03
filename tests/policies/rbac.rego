package app.rbac
default allow = false

# Allow the action if the user is granted permission to perform the action.
allow {
	# unless user location is outside US
	country := data.users[input.user].location.country
	country == "US"
}
