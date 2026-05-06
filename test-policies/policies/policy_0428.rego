package risk.validation.user.check.policy_0428

# Auto-generated policy 428
# Package: risk.validation.user.check

# Metadata
metadata := {
    "policy_id": "0428",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0428_allowed if {
    input.user.role == "admin"
}
policy_0428_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0428_allowed if {
    data.policies.risk.enabled
}
policy_0428_denied if {
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
