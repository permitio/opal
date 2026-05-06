package security.monitoring.policy.deny.policy_0193

# Auto-generated policy 193
# Package: security.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0193",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0193 {
    input.user.role == "admin"
}
denied_0193 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0193 {
    input.user.active
    input.resource.public
}
allowed_0193 {
    data.policies.security.enabled
}

# Utility function for user info
