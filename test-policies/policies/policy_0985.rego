package access.authorization.action.verify.policy_0985

# Auto-generated policy 985
# Package: access.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0985",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0985 {
    input.user.role == "admin"
}
denied_0985 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0985 = false
allowed_0985 {
    data.policies.access.enabled
}

# Utility function for user info
