package governance.validation.action.verify.policy_0541

# Auto-generated policy 541
# Package: governance.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0541",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0541_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0541_allowed if {
    data.policies.governance.enabled
}
policy_0541_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
