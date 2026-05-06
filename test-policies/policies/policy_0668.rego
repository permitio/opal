package governance.validation.policy.deny.policy_0668

# Auto-generated policy 668
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0668",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0668_allowed if {
    input.user.role == "admin"
}
policy_0668_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0668_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
