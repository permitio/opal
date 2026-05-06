package compliance.monitoring.user.verify.policy_0606

# Auto-generated policy 606
# Package: compliance.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0606",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0606 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0606 {
    data.policies.compliance.enabled
}
allowed_0606 {
    input.user.active
    input.resource.public
}

# Utility function for user info
