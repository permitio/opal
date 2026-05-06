package risk.enforcement.context.validate.data.policy_0114

# Auto-generated policy 114
# Package: risk.enforcement.context.validate.data

# Metadata
metadata := {
    "policy_id": "0114",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0114 {
    input.user.role == "admin"
}
denied_0114 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
