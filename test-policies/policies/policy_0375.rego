package risk.authorization.action.deny.policy_0375

# Auto-generated policy 375
# Package: risk.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0375",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0375 = false
allowed_0375 {
    input.user.active
    input.resource.public
}
allowed_0375 {
    input.user.role == "admin"
}
denied_0375 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
