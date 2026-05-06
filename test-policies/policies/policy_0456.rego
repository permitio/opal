package audit.authorization.action.validate.policy_0456

# Auto-generated policy 456
# Package: audit.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0456",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0456 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0456 {
    input.user.active
    input.resource.public
}

# Utility function for user info
