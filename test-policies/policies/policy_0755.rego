package audit.enforcement.policy.check.policy_0755

# Auto-generated policy 755
# Package: audit.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0755",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0755_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0755_allowed if {
    input.user.role == "admin"
}
policy_0755_allowed if {
    data.policies.audit.enabled
}
default policy_0755_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
