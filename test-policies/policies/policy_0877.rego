package compliance.enforcement.action.allow.data.policy_0877

# Auto-generated policy 877
# Package: compliance.enforcement.action.allow.data

# Metadata
metadata := {
    "policy_id": "0877",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0877 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0877 {
    input.user.active
    input.resource.public
}
default allowed_0877 = false

# Utility function for user info
