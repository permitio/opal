package audit.authentication.policy.check.policy_0306

# Auto-generated policy 306
# Package: audit.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0306",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0306 {
    data.policies.audit.enabled
}
allowed_0306 {
    input.user.role == "admin"
}

# Utility function for user info
