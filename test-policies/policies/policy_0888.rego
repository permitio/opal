package audit.monitoring.context.verify.policy_0888

# Auto-generated policy 888
# Package: audit.monitoring.context.verify

# Metadata
metadata := {
    "policy_id": "0888",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0888 = false
allowed_0888 {
    input.user.active
    input.resource.public
}
denied_0888 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
