package governance.monitoring.policy.deny.policy_0709

# Auto-generated policy 709
# Package: governance.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0709",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0709 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0709 {
    data.policies.governance.enabled
}
allowed_0709 {
    input.user.active
    input.resource.public
}

# Utility function for user info
