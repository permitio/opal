package compliance.validation.policy.deny.utils.policy_0002

# Auto-generated policy 2
# Package: compliance.validation.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0002",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0002_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0002_allowed if {
    data.policies.compliance.enabled
}
policy_0002_approved if {
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
