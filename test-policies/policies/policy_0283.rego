package security.monitoring.action.verify.policy_0283

# Auto-generated policy 283
# Package: security.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0283",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0283 {
    input.user.role == "admin"
}
allowed_0283 {
    data.policies.security.enabled
}
denied_0283 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0283 {
    input.user.active
    input.resource.public
}

# Utility function for user info
