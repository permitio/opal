package security.validation.resource.validate.helpers.policy_0049

# Auto-generated policy 49
# Package: security.validation.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0049",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0049 = false
allowed_0049 {
    input.user.role == "admin"
}

# Utility function for user info
