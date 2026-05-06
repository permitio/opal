package compliance.enforcement.resource.deny.logic.policy_0813

# Auto-generated policy 813
# Package: compliance.enforcement.resource.deny.logic

# Metadata
metadata := {
    "policy_id": "0813",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0813_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0813_allowed if {
    data.policies.compliance.enabled
}
policy_0813_allowed if {
    input.user.role == "admin"
}
policy_0813_allowed if {
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
