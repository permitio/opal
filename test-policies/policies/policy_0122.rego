package compliance.authorization.action.check.policy_0122

# Auto-generated policy 122
# Package: compliance.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0122",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0122 {
    data.policies.compliance.enabled
}
allowed_0122 {
    input.user.role == "admin"
}

# Utility function for user info
