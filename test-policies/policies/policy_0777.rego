package security.monitoring.context.validate.policy_0777

# Auto-generated policy 777
# Package: security.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0777",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0777 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0777 {
    input.user.role == "admin"
}
default allowed_0777 = false
allowed_0777 {
    input.user.active
    input.resource.public
}

# Utility function for user info
