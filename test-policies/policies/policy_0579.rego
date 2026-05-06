package risk.validation.user.deny.policy_0579

# Auto-generated policy 579
# Package: risk.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0579",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0579_allowed = false
policy_0579_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0579_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
