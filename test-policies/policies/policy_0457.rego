package access.monitoring.action.deny.policy_0457

# Auto-generated policy 457
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0457",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0457 {
    input.user.role == "admin"
}
allowed_0457 {
    input.user.active
    input.resource.public
}
denied_0457 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0457 {
    data.policies.access.enabled
}

# Utility function for user info
