package risk.monitoring.user.verify.policy_0938

# Auto-generated policy 938
# Package: risk.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0938",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0938 {
    input.user.active
    input.resource.public
}
denied_0938 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0938 {
    input.user.role == "admin"
}
allowed_0938 {
    data.policies.risk.enabled
}

# Utility function for user info
