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
policy_0424_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0424_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
