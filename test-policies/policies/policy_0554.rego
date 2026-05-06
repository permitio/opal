package compliance.validation.resource.allow.policy_0554

# Auto-generated policy 554
# Package: compliance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0554",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0554_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0554_allowed if {
    input.user.role == "admin"
}
default policy_0554_allowed = false
policy_0554_allowed if {
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
