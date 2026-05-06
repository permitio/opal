package access.validation.user.validate.policy_0483

# Auto-generated policy 483
# Package: access.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0483",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0483 = false
allowed_0483 {
    input.user.role == "admin"
}

# Utility function for user info
