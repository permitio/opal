package compliance.authorization.policy.check.logic.policy_0936

# Auto-generated policy 936
# Package: compliance.authorization.policy.check.logic

# Metadata
metadata := {
    "policy_id": "0936",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0936 {
    input.user.active
    input.resource.public
}
denied_0936 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0936 {
    data.policies.compliance.enabled
}

# Utility function for user info
