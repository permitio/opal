package governance.authentication.policy.allow.utils.policy_0431

# Auto-generated policy 431
# Package: governance.authentication.policy.allow.utils

# Metadata
metadata := {
    "policy_id": "0431",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0431 {
    input.user.role == "admin"
}
default allowed_0431 = false

# Utility function for user info
