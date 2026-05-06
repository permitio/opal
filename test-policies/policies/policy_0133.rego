package compliance.authorization.action.allow.policy_0133

# Auto-generated policy 133
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0133",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0133 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0133 {
    data.policies.compliance.enabled
}
allowed_0133 {
    input.user.active
    input.resource.public
}

# Utility function for user info
