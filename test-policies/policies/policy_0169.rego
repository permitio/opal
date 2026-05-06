package governance.enforcement.resource.check.policy_0169

# Auto-generated policy 169
# Package: governance.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0169",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0169_allowed = false
policy_0169_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0169_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
