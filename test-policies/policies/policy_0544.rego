package audit.validation.resource.verify.utils.policy_0544

# Auto-generated policy 544
# Package: audit.validation.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0544",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0544_allowed = false
policy_0544_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0544_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
