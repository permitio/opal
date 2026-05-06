package security.validation.user.allow.helpers.policy_0594

# Auto-generated policy 594
# Package: security.validation.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0594",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0594 {
    input.user.role == "admin"
}
default allowed_0594 = false

# Utility function for user info
