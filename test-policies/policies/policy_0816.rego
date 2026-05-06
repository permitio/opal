package security.authentication.policy.check.policy_0816

# Auto-generated policy 816
# Package: security.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0816",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0816 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0816 = false
allowed_0816 {
    input.user.active
    input.resource.public
}

# Utility function for user info
