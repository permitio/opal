package governance.validation.context.allow.logic.policy_0814

# Auto-generated policy 814
# Package: governance.validation.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0814",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0814_allowed if {
    input.user.active
    input.resource.public
}
policy_0814_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0814_allowed if {
    data.policies.governance.enabled
}
policy_0814_denied if {
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
