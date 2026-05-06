package compliance.monitoring.policy.allow.policy_0232

# Auto-generated policy 232
# Package: compliance.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0232",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0232 {
    input.user.role == "admin"
}
allowed_0232 {
    input.user.active
    input.resource.public
}

# Utility function for user info
