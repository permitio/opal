package compliance.monitoring.user.deny.utils.policy_0513

# Auto-generated policy 513
# Package: compliance.monitoring.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0513",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0513 {
    data.policies.compliance.enabled
}
denied_0513 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0513 {
    input.user.active
    input.resource.public
}
allowed_0513 {
    input.user.role == "admin"
}

# Utility function for user info
