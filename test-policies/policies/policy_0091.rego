package compliance.authorization.resource.verify.helpers.policy_0091

# Auto-generated policy 91
# Package: compliance.authorization.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0091",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0091_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0091_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0091_allowed if {
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
