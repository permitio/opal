package audit.authorization.context.allow.policy_0589

# Auto-generated policy 589
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0589",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0589 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0589 {
    data.policies.audit.enabled
}

# Utility function for user info
