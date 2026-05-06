package security.authorization.context.deny.utils.policy_0728

# Auto-generated policy 728
# Package: security.authorization.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0728",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0728 {
    input.user.role == "admin"
}
default allowed_0728 = false
denied_0728 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
