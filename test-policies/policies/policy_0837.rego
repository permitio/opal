package compliance.enforcement.user.deny.policy_0837

# Auto-generated policy 837
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0837",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0837_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0837_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
