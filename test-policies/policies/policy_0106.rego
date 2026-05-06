package audit.authorization.context.check.policy_0106

# Auto-generated policy 106
# Package: audit.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0106",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0106 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0106 {
    data.policies.audit.enabled
}
allowed_0106 {
    input.user.active
    input.resource.public
}

# Utility function for user info
