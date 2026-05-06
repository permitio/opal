package risk.authentication.user.allow.policy_0072

# Auto-generated policy 72
# Package: risk.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0072",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0072 {
    input.user.active
    input.resource.public
}
denied_0072 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0072 {
    input.user.role == "admin"
}

# Utility function for user info
