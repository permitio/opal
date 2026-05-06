package risk.enforcement.policy.verify.utils.policy_0504

# Auto-generated policy 504
# Package: risk.enforcement.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0504",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0504_allowed if {
    data.policies.risk.enabled
}
policy_0504_allowed if {
    input.user.role == "admin"
}
default policy_0504_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
