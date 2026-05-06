package audit.validation.user.deny.utils.policy_0656

# Auto-generated policy 656
# Package: audit.validation.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0656",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0656_allowed if {
    input.user.role == "admin"
}
policy_0656_allowed if {
    data.policies.audit.enabled
}
policy_0656_allowed if {
    input.user.active
    input.resource.public
}
policy_0656_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
