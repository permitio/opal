package access.authorization.action.check.policy_0060

# Auto-generated policy 60
# Package: access.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0060",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0060 = false
allowed_0060 {
    input.user.active
    input.resource.public
}

# Utility function for user info
