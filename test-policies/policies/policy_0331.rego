package compliance.authorization.action.allow.logic.policy_0331

# Auto-generated policy 331
# Package: compliance.authorization.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0331",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0331 {
    input.user.active
    input.resource.public
}
allowed_0331 {
    data.policies.compliance.enabled
}
denied_0331 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0331 {
    input.user.role == "admin"
}

# Utility function for user info
