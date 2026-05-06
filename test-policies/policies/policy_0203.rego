package risk.authorization.policy.verify.data.policy_0203

# Auto-generated policy 203
# Package: risk.authorization.policy.verify.data

# Metadata
metadata := {
    "policy_id": "0203",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0203_allowed = false
policy_0203_allowed if {
    input.user.role == "admin"
}
policy_0203_denied if {
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
