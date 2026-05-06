package audit.authorization.policy.validate.policy_0872

# Auto-generated policy 872
# Package: audit.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0872",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0872 {
    input.user.active
    input.resource.public
}
denied_0872 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0872 {
    input.user.role == "admin"
}
default allowed_0872 = false

# Utility function for user info
