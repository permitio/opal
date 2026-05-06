package risk.validation.policy.allow.utils.policy_0228

# Auto-generated policy 228
# Package: risk.validation.policy.allow.utils

# Metadata
metadata := {
    "policy_id": "0228",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0228_allowed if {
    input.user.role == "admin"
}
policy_0228_allowed if {
    data.policies.risk.enabled
}
default policy_0228_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
