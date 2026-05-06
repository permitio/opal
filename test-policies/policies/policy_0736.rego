package risk.validation.resource.check.utils.policy_0736

# Auto-generated policy 736
# Package: risk.validation.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0736",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0736_allowed = false
policy_0736_allowed if {
    input.user.role == "admin"
}
policy_0736_denied if {
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
