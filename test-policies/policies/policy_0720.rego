package compliance.validation.action.verify.core.policy_0720

# Auto-generated policy 720
# Package: compliance.validation.action.verify.core

# Metadata
metadata := {
    "policy_id": "0720",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0720_allowed if {
    input.user.active
    input.resource.public
}
policy_0720_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0720_allowed = false
policy_0720_allowed if {
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
