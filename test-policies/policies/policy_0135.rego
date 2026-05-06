package risk.enforcement.context.deny.policy_0135

# Auto-generated policy 135
# Package: risk.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0135",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0135 {
    input.user.role == "admin"
}
allowed_0135 {
    input.user.active
    input.resource.public
}
default allowed_0135 = false
denied_0135 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
