package audit.monitoring.context.deny.policy_0795

# Auto-generated policy 795
# Package: audit.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0795",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0795 {
    input.user.role == "admin"
}
default allowed_0795 = false
denied_0795 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0795 {
    input.user.active
    input.resource.public
}

# Utility function for user info
