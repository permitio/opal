package security.validation.resource.deny.helpers.policy_0405

# Auto-generated policy 405
# Package: security.validation.resource.deny.helpers

# Metadata
metadata := {
    "policy_id": "0405",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0405_allowed if {
    input.user.role == "admin"
}
default policy_0405_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
