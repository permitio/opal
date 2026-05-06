package security.authentication.context.deny.core.policy_0481

# Auto-generated policy 481
# Package: security.authentication.context.deny.core

# Metadata
metadata := {
    "policy_id": "0481",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0481 {
    data.policies.security.enabled
}
default allowed_0481 = false
allowed_0481 {
    input.user.role == "admin"
}

# Utility function for user info
