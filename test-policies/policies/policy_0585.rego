package audit.enforcement.policy.check.core.policy_0585

# Auto-generated policy 585
# Package: audit.enforcement.policy.check.core

# Metadata
metadata := {
    "policy_id": "0585",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0585_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0585_allowed = false
policy_0585_allowed if {
    input.user.active
    input.resource.public
}
policy_0585_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
