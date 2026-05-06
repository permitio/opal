package audit.enforcement.context.validate.policy_0053

# Auto-generated policy 53
# Package: audit.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0053",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0053 {
    input.user.active
    input.resource.public
}
denied_0053 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
