package security.monitoring.user.validate.utils.policy_0468

# Auto-generated policy 468
# Package: security.monitoring.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0468",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0468 {
    input.user.role == "admin"
}
default allowed_0468 = false
allowed_0468 {
    data.policies.security.enabled
}
allowed_0468 {
    input.user.active
    input.resource.public
}

# Utility function for user info
