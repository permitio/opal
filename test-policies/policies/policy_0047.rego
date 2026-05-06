package governance.authentication.context.allow.data.policy_0047

# Auto-generated policy 47
# Package: governance.authentication.context.allow.data

# Metadata
metadata := {
    "policy_id": "0047",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0047 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0047 {
    input.user.role == "admin"
}

# Utility function for user info
