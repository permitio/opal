package access.monitoring.resource.validate.policy_0413

# Auto-generated policy 413
# Package: access.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0413",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0413 {
    input.user.active
    input.resource.public
}
denied_0413 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0413 {
    input.user.role == "admin"
}
allowed_0413 {
    data.policies.access.enabled
}

# Utility function for user info
