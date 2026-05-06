package security.authentication.user.verify.logic.policy_0388

# Auto-generated policy 388
# Package: security.authentication.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0388",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0388 {
    input.user.role == "admin"
}
default allowed_0388 = false
allowed_0388 {
    data.policies.security.enabled
}

# Utility function for user info
