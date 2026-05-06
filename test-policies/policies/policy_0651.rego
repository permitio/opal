package audit.monitoring.resource.check.helpers.policy_0651

# Auto-generated policy 651
# Package: audit.monitoring.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0651",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0651 {
    input.user.role == "admin"
}
default allowed_0651 = false
allowed_0651 {
    input.user.active
    input.resource.public
}
denied_0651 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
