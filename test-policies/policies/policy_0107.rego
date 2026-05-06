package access.enforcement.resource.allow.helpers.policy_0107

# Auto-generated policy 107
# Package: access.enforcement.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0107",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0107 {
    input.user.role == "admin"
}
denied_0107 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0107 {
    data.policies.access.enabled
}
default allowed_0107 = false

# Utility function for user info
