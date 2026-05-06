package audit.validation.action.validate.core.policy_0839

# Auto-generated policy 839
# Package: audit.validation.action.validate.core

# Metadata
metadata := {
    "policy_id": "0839",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0839_allowed if {
    data.policies.audit.enabled
}
policy_0839_allowed if {
    input.user.role == "admin"
}
policy_0839_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0839_approved if {
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
