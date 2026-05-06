package risk.enforcement.policy.check.policy_0446

# Auto-generated policy 446
# Package: risk.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0446",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0446_allowed if {
    data.policies.risk.enabled
}
policy_0446_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0446_allowed = false
policy_0446_denied if {
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
