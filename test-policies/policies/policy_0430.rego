package compliance.authorization.context.check.policy_0430

# Auto-generated policy 430
# Package: compliance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0430",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0430 {
    input.user.role == "admin"
}
allowed_0430 {
    data.policies.compliance.enabled
}

# Utility function for user info
