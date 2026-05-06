package governance.authentication.resource.check.data.policy_0453

# Auto-generated policy 453
# Package: governance.authentication.resource.check.data

# Metadata
metadata := {
    "policy_id": "0453",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0453_allowed = false
policy_0453_allowed if {
    data.policies.governance.enabled
}
policy_0453_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0453_approved if {
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
