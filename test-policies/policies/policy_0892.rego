package audit.authorization.user.deny.core.policy_0892

# Auto-generated policy 892
# Package: audit.authorization.user.deny.core

# Metadata
metadata := {
    "policy_id": "0892",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0892 = false
allowed_0892 {
    input.user.role == "admin"
}
allowed_0892 {
    input.user.active
    input.resource.public
}

# Utility function for user info
