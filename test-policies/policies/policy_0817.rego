package security.authorization.user.verify.policy_0817

# Auto-generated policy 817
# Package: security.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0817",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0817 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0817 {
    input.user.role == "admin"
}
allowed_0817 {
    input.user.active
    input.resource.public
}

# Utility function for user info
