package governance.monitoring.policy.allow.policy_0494

# Auto-generated policy 494
# Package: governance.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0494",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0494 {
    input.user.role == "admin"
}
denied_0494 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0494 {
    input.user.active
    input.resource.public
}
allowed_0494 {
    data.policies.governance.enabled
}

# Utility function for user info
