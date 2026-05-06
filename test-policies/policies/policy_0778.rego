package governance.authentication.context.allow.policy_0778

# Auto-generated policy 778
# Package: governance.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0778",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0778 = false
allowed_0778 {
    input.user.role == "admin"
}
allowed_0778 {
    input.user.active
    input.resource.public
}

# Utility function for user info
