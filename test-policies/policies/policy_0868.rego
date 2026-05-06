package audit.authorization.resource.deny.data.policy_0868

# Auto-generated policy 868
# Package: audit.authorization.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0868",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0868 {
    input.user.active
    input.resource.public
}
denied_0868 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0868 {
    input.user.role == "admin"
}

# Utility function for user info
