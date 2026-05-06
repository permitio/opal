package compliance.monitoring.policy.allow.policy_0844

# Auto-generated policy 844
# Package: compliance.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0844",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0844 {
    input.user.active
    input.resource.public
}
allowed_0844 {
    data.policies.compliance.enabled
}
denied_0844 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
