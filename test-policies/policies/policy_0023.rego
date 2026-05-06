package audit.authorization.user.check.policy_0023

# Auto-generated policy 23
# Package: audit.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0023",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0023 = false
allowed_0023 {
    input.user.active
    input.resource.public
}
allowed_0023 {
    data.policies.audit.enabled
}
denied_0023 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
