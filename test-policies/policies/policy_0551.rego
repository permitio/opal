package access.authorization.action.validate.policy_0551

# Auto-generated policy 551
# Package: access.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0551",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0551 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0551 {
    data.policies.access.enabled
}
allowed_0551 {
    input.user.role == "admin"
}

# Utility function for user info
