package compliance.monitoring.context.allow.logic.policy_0575

# Auto-generated policy 575
# Package: compliance.monitoring.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0575",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0575 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0575 {
    input.user.active
    input.resource.public
}

# Utility function for user info
