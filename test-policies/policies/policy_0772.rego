package governance.authorization.policy.allow.core.policy_0772

# Auto-generated policy 772
# Package: governance.authorization.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0772",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0772 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0772 {
    input.user.active
    input.resource.public
}
allowed_0772 {
    input.user.role == "admin"
}

# Utility function for user info
