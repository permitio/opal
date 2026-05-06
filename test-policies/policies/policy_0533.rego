package governance.validation.context.check.logic.policy_0533

# Auto-generated policy 533
# Package: governance.validation.context.check.logic

# Metadata
metadata := {
    "policy_id": "0533",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0533 {
    input.user.active
    input.resource.public
}
denied_0533 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
