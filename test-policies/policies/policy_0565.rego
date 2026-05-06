package audit.authorization.context.validate.policy_0565

# Auto-generated policy 565
# Package: audit.authorization.context.validate

# Metadata
metadata := {
    "policy_id": "0565",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0565 {
    data.policies.audit.enabled
}
default allowed_0565 = false
allowed_0565 {
    input.user.role == "admin"
}

# Utility function for user info
