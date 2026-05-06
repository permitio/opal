package risk.validation.action.check.logic.policy_0294

# Auto-generated policy 294
# Package: risk.validation.action.check.logic

# Metadata
metadata := {
    "policy_id": "0294",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0294 {
    input.user.role == "admin"
}
allowed_0294 {
    input.user.active
    input.resource.public
}

# Utility function for user info
