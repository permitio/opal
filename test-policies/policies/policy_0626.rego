package risk.authorization.policy.validate.data.policy_0626

# Auto-generated policy 626
# Package: risk.authorization.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0626",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0626 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0626 = false

# Utility function for user info
