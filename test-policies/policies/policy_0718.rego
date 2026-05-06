package risk.authorization.user.validate.policy_0718

# Auto-generated policy 718
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0718",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0718 {
    input.user.active
    input.resource.public
}
denied_0718 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
