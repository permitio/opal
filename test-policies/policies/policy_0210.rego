package access.authentication.resource.allow.logic.policy_0210

# Auto-generated policy 210
# Package: access.authentication.resource.allow.logic

# Metadata
metadata := {
    "policy_id": "0210",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0210 = false
allowed_0210 {
    data.policies.access.enabled
}
allowed_0210 {
    input.user.role == "admin"
}
denied_0210 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
