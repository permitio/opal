package access.authorization.context.verify.data.policy_0042

# Auto-generated policy 42
# Package: access.authorization.context.verify.data

# Metadata
metadata := {
    "policy_id": "0042",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0042 {
    input.user.active
    input.resource.public
}
allowed_0042 {
    input.user.role == "admin"
}

# Utility function for user info
