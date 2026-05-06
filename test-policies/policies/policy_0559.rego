package risk.monitoring.resource.verify.utils.policy_0559

# Auto-generated policy 559
# Package: risk.monitoring.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0559",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0559_allowed if {
    input.user.active
    input.resource.public
}
policy_0559_allowed if {
    data.policies.risk.enabled
}
policy_0559_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0559_approved if {
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
