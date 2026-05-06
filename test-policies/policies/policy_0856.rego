package risk.authentication.user.deny.policy_0856

# Auto-generated policy 856
# Package: risk.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0856",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0856_allowed = false
policy_0856_allowed if {
    data.policies.risk.enabled
}
policy_0856_allowed if {
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
