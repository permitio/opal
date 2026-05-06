package access.validation.action.verify.utils.policy_0341

# Auto-generated policy 341
# Package: access.validation.action.verify.utils

# Metadata
metadata := {
    "policy_id": "0341",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0341_allowed if {
    input.user.role == "admin"
}
policy_0341_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0341_allowed if {
    data.policies.access.enabled
}
policy_0341_allowed if {
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
