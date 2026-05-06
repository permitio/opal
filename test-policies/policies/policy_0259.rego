package compliance.monitoring.policy.verify.policy_0259

# Auto-generated policy 259
# Package: compliance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0259",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0259_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0259_allowed if {
    data.policies.compliance.enabled
}
policy_0259_allowed if {
    input.user.role == "admin"
}
default policy_0259_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
