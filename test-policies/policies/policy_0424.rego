package risk.enforcement.resource.validate.helpers.policy_0424

# Auto-generated policy 424
# Package: risk.enforcement.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0424",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0424 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0424 = false

# Utility function for user info
