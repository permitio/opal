package governance.authentication.context.allow.policy_0043

# Auto-generated policy 43
# Package: governance.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0043",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0043 {
    input.user.role == "admin"
}
allowed_0043 {
    input.user.active
    input.resource.public
}

# Utility function for user info
