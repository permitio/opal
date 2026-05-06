package audit.enforcement.policy.allow.policy_0573

# Auto-generated policy 573
# Package: audit.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0573",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0573_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0573_allowed if {
    data.policies.audit.enabled
}
policy_0573_denied if {
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
