package security.validation.policy.check.helpers.policy_0226

# Auto-generated policy 226
# Package: security.validation.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0226",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0226 = false
allowed_0226 {
    input.user.active
    input.resource.public
}

# Utility function for user info
