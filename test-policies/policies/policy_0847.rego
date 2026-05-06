package audit.authentication.policy.allow.data.policy_0847

# Auto-generated policy 847
# Package: audit.authentication.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0847",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0847 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0847 {
    data.policies.audit.enabled
}
allowed_0847 {
    input.user.active
    input.resource.public
}

# Utility function for user info
