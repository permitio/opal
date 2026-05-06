package governance.validation.resource.deny.policy_0016

# Auto-generated policy 16
# Package: governance.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0016",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0016_allowed if {
    input.user.role == "admin"
}
policy_0016_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0016_allowed if {
    data.policies.governance.enabled
}
policy_0016_denied if {
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
