package access.enforcement.action.deny.policy_0225

# Auto-generated policy 225
# Package: access.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0225",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0225 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0225 {
    data.policies.access.enabled
}

# Utility function for user info
