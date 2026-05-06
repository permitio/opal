package risk.enforcement.action.validate.policy_0274

# Auto-generated policy 274
# Package: risk.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0274",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0274 {
    input.user.active
    input.resource.public
}
denied_0274 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
