package compliance.validation.resource.verify.utils.policy_0545

# Auto-generated policy 545
# Package: compliance.validation.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0545",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0545_allowed if {
    data.policies.compliance.enabled
}
policy_0545_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0545_allowed if {
    input.user.role == "admin"
}
default policy_0545_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
