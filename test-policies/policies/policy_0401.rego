package compliance.authorization.context.check.policy_0401

# Auto-generated policy 401
# Package: compliance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0401",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0401 = false
allowed_0401 {
    input.user.active
    input.resource.public
}

# Utility function for user info
