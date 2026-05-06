package compliance.enforcement.policy.check.helpers.policy_0734

# Auto-generated policy 734
# Package: compliance.enforcement.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0734",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0734_allowed = false
policy_0734_approved if {
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
