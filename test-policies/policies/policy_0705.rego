package compliance.validation.policy.deny.policy_0705

# Auto-generated policy 705
# Package: compliance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0705",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0705_allowed if {
    input.user.active
    input.resource.public
}
policy_0705_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0705_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0705_allowed if {
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
