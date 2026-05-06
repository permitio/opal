package risk.authentication.policy.verify.policy_0792

# Auto-generated policy 792
# Package: risk.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0792",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0792_allowed if {
    data.policies.risk.enabled
}
policy_0792_allowed if {
    input.user.role == "admin"
}
policy_0792_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0792_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
