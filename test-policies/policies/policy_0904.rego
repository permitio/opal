package compliance.monitoring.context.check.policy_0904

# Auto-generated policy 904
# Package: compliance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0904",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0904 {
    input.user.active
    input.resource.public
}
denied_0904 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
