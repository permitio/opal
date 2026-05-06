package governance.validation.policy.deny.policy_0696

# Auto-generated policy 696
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0696",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0696_allowed if {
    data.policies.governance.enabled
}
policy_0696_denied if {
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
