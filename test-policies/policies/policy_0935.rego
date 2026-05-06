package access.validation.context.validate.policy_0935

# Auto-generated policy 935
# Package: access.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0935",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0935 = false
allowed_0935 {
    input.user.role == "admin"
}

# Utility function for user info
