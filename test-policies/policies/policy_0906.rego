package compliance.validation.resource.allow.policy_0906

# Auto-generated policy 906
# Package: compliance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0906",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0906_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0906_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0906_allowed if {
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
