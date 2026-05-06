package risk.validation.policy.verify.policy_0905

# Auto-generated policy 905
# Package: risk.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0905",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0905_allowed = false
policy_0905_denied if {
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
