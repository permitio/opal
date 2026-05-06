package audit.validation.user.allow.policy_0038

# Auto-generated policy 38
# Package: audit.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0038",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0038 = false
allowed_0038 {
    input.user.active
    input.resource.public
}

# Utility function for user info
