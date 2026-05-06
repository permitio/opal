package audit.monitoring.user.deny.policy_0236

# Auto-generated policy 236
# Package: audit.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0236",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0236 {
    input.user.active
    input.resource.public
}
allowed_0236 {
    input.user.role == "admin"
}
allowed_0236 {
    data.policies.audit.enabled
}
denied_0236 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
