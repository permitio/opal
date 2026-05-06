package audit.authentication.context.allow.policy_0140

# Auto-generated policy 140
# Package: audit.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0140",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0140 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0140 {
    data.policies.audit.enabled
}
allowed_0140 {
    input.user.active
    input.resource.public
}
default allowed_0140 = false

# Utility function for user info
