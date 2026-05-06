package compliance.authorization.resource.verify.logic.policy_0051

# Auto-generated policy 51
# Package: compliance.authorization.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0051",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0051_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0051_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0051_allowed if {
    data.policies.compliance.enabled
}
policy_0051_allowed if {
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
