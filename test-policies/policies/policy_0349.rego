package risk.enforcement.policy.verify.utils.policy_0349

# Auto-generated policy 349
# Package: risk.enforcement.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0349",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0349_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0349_allowed if {
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
