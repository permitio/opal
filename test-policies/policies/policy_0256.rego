package security.authentication.user.check.core.policy_0256

# Auto-generated policy 256
# Package: security.authentication.user.check.core

# Metadata
metadata := {
    "policy_id": "0256",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0256 = false
allowed_0256 {
    data.policies.security.enabled
}
denied_0256 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
