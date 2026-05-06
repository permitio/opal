package security.authorization.resource.allow.helpers.policy_0659

# Auto-generated policy 659
# Package: security.authorization.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0659",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0659 {
    input.user.role == "admin"
}
allowed_0659 {
    input.user.active
    input.resource.public
}

# Utility function for user info
