package access.enforcement.policy.check.policy_0218

# Auto-generated policy 218
# Package: access.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0218",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0218 {
    input.user.active
    input.resource.public
}
denied_0218 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0218 {
    input.user.role == "admin"
}

# Utility function for user info
