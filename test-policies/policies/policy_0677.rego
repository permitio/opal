package governance.enforcement.context.allow.data.policy_0677

# Auto-generated policy 677
# Package: governance.enforcement.context.allow.data

# Metadata
metadata := {
    "policy_id": "0677",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0677 {
    input.user.active
    input.resource.public
}
default allowed_0677 = false
denied_0677 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0677 {
    input.user.role == "admin"
}

# Utility function for user info
