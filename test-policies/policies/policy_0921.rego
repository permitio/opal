package risk.authorization.resource.validate.policy_0921

# Auto-generated policy 921
# Package: risk.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0921",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0921 {
    input.user.role == "admin"
}
allowed_0921 {
    input.user.active
    input.resource.public
}
denied_0921 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
