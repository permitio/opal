package compliance.authentication.user.validate.policy_0445

# Auto-generated policy 445
# Package: compliance.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0445",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0445_allowed = false
policy_0445_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0445_allowed if {
    data.policies.compliance.enabled
}
policy_0445_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
